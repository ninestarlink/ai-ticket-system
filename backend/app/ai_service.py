import json
import logging
import re
import time
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .mock_data import TOOL_SCHEMAS, execute_tool
from .models import Analysis, Ticket, ToolCall, now_iso
from .notify import auto_notify_if_needed
from .prompts import REPAIR_PROMPT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

CATEGORIES = ("技术问题", "支付与退款", "其他")
PRIORITIES = ("高", "中", "低")

CATEGORY_ROUTING = {
    "技术问题": ("技术组", "陈工"),
    "支付与退款": ("售后组", "李静"),
    "其他": ("客服组", "王琳"),
}

MAX_TOOL_ROUNDS = 3


class LLMError(Exception):
    """模型调用或输出解析失败。"""


class LLMClient:
    """对 OpenAI 兼容接口的最小封装，便于测试中替换 chat 方法。"""

    def __init__(self) -> None:
        if not settings.model_api_key:
            raise LLMError("未配置 MODEL_API_KEY，无法调用模型")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError("缺少 openai 依赖") from exc
        self.model = settings.model_name
        self.client = OpenAI(
            api_key=settings.model_api_key,
            base_url=settings.model_base_url,
            timeout=settings.model_timeout,
        )

    def chat(self, messages: list, tools: Optional[list] = None) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"模型调用失败：{exc}") from exc

        message = response.choices[0].message
        calls = []
        for call in message.tool_calls or []:
            calls.append(
                {
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": call.function.arguments or "{}",
                }
            )
        return {"content": message.content or "", "tool_calls": calls}


def _assistant_message(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.get("content") or None,
        "tool_calls": [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": call["arguments"],
                },
            }
            for call in result.get("tool_calls") or []
        ],
    }


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except ValueError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _normalize_category(value: Any) -> str:
    text = str(value or "").strip()
    if "技术" in text:
        return "技术问题"
    if "支付" in text or "退款" in text or "扣款" in text:
        return "支付与退款"
    return "其他"


def _normalize_priority(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in ("高", "high", "urgent", "p0"):
        return "高"
    if text in ("低", "low", "p2"):
        return "低"
    if text in ("中", "medium", "normal", "p1"):
        return "中"
    if "高" in text:
        return "高"
    if "低" in text:
        return "低"
    return "中"


def _validate(data: Dict[str, Any]) -> Dict[str, str]:
    category = _normalize_category(data.get("category"))
    priority = _normalize_priority(data.get("priority"))
    summary = str(data.get("summary") or "").strip()
    suggestion = str(data.get("suggestion") or "").strip()

    if not summary:
        raise LLMError("模型输出缺少摘要 summary")
    if not suggestion:
        raise LLMError("模型输出缺少处理建议 suggestion")

    return {
        "category": category,
        "priority": priority,
        "summary": summary[:200],
        "suggestion": suggestion[:1000],
    }


def _apply_evidence_guard(
    data: Dict[str, str], evidence: list
) -> Dict[str, str]:
    """依据真实工具结果做一致性校正，不生成任何虚构内容。

    题目规定“经工具查询核实的重复扣款”为高优先级。若工具确实返回同一订单
    存在 2 笔及以上成功支付，则校正类别与优先级，避免模型随机性影响验收事实。
    """
    for name, _arguments, result in evidence:
        if name != "query_payment" or not isinstance(result, dict):
            continue
        payments = result.get("payments") or []
        success = [
            item
            for item in payments
            if "成功" in str(item.get("status", ""))
        ]
        if result.get("count", 0) >= 2 and len(success) >= 2:
            data["category"] = "支付与退款"
            data["priority"] = "高"
            break
    return data


def _build_user_message(ticket: Ticket) -> str:
    if ticket.order_id:
        source = "客户填写" if ticket.order_id_source == "field" else "从问题描述中识别"
        order_line = f"系统识别到的订单号：{ticket.order_id}（来源：{source}）"
    else:
        order_line = "系统识别到的订单号：无"
    return (
        f"客户姓名：{ticket.name}\n"
        f"提交内容：{ticket.description}\n"
        f"{order_line}\n"
        "请按系统要求分析，并只输出 JSON。"
    )


def _mark_failed(db: Session, ticket_id: int, analysis_id: Optional[int], error: str, latency_ms: int) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass
    if analysis_id:
        row = db.get(Analysis, analysis_id)
        if row:
            row.status = "failed"
            row.error = error[:2000]
            row.latency_ms = latency_ms
    ticket = db.get(Ticket, ticket_id)
    if ticket:
        ticket.analysis_state = "failed"
        ticket.updated_at = now_iso()
    db.commit()


def run_analysis(ticket_id: int) -> None:
    """后台执行：调模型 → 工具循环 → 落库 → 高优先级通知。"""
    started = time.time()
    db = SessionLocal()
    analysis: Optional[Analysis] = None
    final_content = ""
    try:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return

        analysis = Analysis(
            ticket_id=ticket_id,
            status="running",
            model=settings.model_name,
            created_at=now_iso(),
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        ticket.current_analysis_id = analysis.id
        db.commit()

        client = LLMClient()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(ticket)},
        ]

        data: Optional[Dict[str, Any]] = None
        evidence = []
        for _ in range(MAX_TOOL_ROUNDS):
            result = client.chat(messages, TOOL_SCHEMAS)
            calls = result.get("tool_calls") or []

            if calls:
                messages.append(_assistant_message(result))
                for call in calls:
                    try:
                        arguments = json.loads(call.get("arguments") or "{}")
                    except ValueError:
                        arguments = {"_raw": call.get("arguments")}
                    if not isinstance(arguments, dict):
                        arguments = {"_raw": arguments}
                    tool_result = execute_tool(call["name"], arguments)
                    evidence.append((call["name"], arguments, tool_result))
                    db.add(
                        ToolCall(
                            analysis_id=analysis.id,
                            ticket_id=ticket_id,
                            name=call["name"],
                            arguments=json.dumps(arguments, ensure_ascii=False),
                            result=json.dumps(tool_result, ensure_ascii=False),
                            ok=bool(tool_result.get("ok", True)),
                            created_at=now_iso(),
                        )
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(tool_result, ensure_ascii=False),
                        }
                    )
                db.commit()
                continue

            final_content = result.get("content") or ""
            data = _extract_json(final_content)
            if data:
                break

            # 输出不是合法 JSON：让模型修复一次
            messages.append({"role": "assistant", "content": final_content})
            messages.append({"role": "user", "content": REPAIR_PROMPT})
            repaired = client.chat(messages, None)
            final_content = repaired.get("content") or ""
            data = _extract_json(final_content)
            break

        if not data:
            raise LLMError("模型输出无法解析为 JSON")

        normalized = _validate(data)
        normalized = _apply_evidence_guard(normalized, evidence)
        latency = int((time.time() - started) * 1000)
        analysis.status = "success"
        analysis.category = normalized["category"]
        analysis.priority = normalized["priority"]
        analysis.summary = normalized["summary"]
        analysis.suggestion = normalized["suggestion"]
        analysis.raw_output = final_content[:4000]
        analysis.latency_ms = latency

        department, assignee = CATEGORY_ROUTING[normalized["category"]]
        ticket.category = normalized["category"]
        ticket.priority = normalized["priority"]
        ticket.department = department
        ticket.assignee = assignee
        ticket.analysis_state = "success"
        ticket.updated_at = now_iso()
        db.commit()

        if normalized["priority"] == "高":
            auto_notify_if_needed(ticket_id, analysis.id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("工单分析失败 ticket=%s", ticket_id)
        latency = int((time.time() - started) * 1000)
        _mark_failed(db, ticket_id, analysis.id if analysis else None, str(exc), latency)
    finally:
        db.close()


def trigger_analysis(ticket_id: int, background_tasks) -> bool:
    """把工单标记为分析中并投递后台任务，返回是否成功投递。"""
    db = SessionLocal()
    try:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return False
        if ticket.analysis_state == "running":
            return False
        ticket.analysis_state = "running"
        ticket.updated_at = now_iso()
        db.commit()
    finally:
        db.close()

    background_tasks.add_task(run_analysis, ticket_id)
    return True
