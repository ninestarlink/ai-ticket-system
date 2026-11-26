import json
import logging
import threading
from typing import Any, Dict, Optional

import httpx

from .config import settings
from .database import SessionLocal
from .models import Analysis, Notification, Ticket, now_iso

logger = logging.getLogger(__name__)

# 单进程内串行化通知操作，避免并发请求导致同一条工单重复发送
_notify_lock = threading.Lock()


class NotifyNotAllowed(Exception):
    """当前工单的通知状态不允许重试。"""


def _build_text(ticket: Ticket, analysis: Analysis) -> str:
    return (
        "【高优先级工单】\n"
        f"工单编号：{ticket.ticket_no}\n"
        f"问题摘要：{analysis.summary or '（无摘要）'}\n"
        f"优先级：{analysis.priority or '高'}\n"
        f"部门：{ticket.department or '（未分配）'}\n"
        f"负责人：{ticket.assignee or '（未分配）'}"
    )


def _parse_json(text: Optional[str]) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def notification_to_dict(row: Notification) -> Dict[str, Any]:
    return {
        "id": row.id,
        "ticket_id": row.ticket_id,
        "analysis_id": row.analysis_id,
        "status": row.status,
        "http_status": row.http_status,
        "error": row.error,
        "request_body": _parse_json(row.request_body),
        "response_body": _parse_json(row.response_body),
        "created_at": row.created_at,
        "finished_at": row.finished_at,
    }


def _has_success(db, ticket_id: int) -> bool:
    return (
        db.query(Notification)
        .filter(Notification.ticket_id == ticket_id, Notification.status == "success")
        .count()
        > 0
    )


def _latest(db, ticket_id: int) -> Optional[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.ticket_id == ticket_id)
        .order_by(Notification.id.desc())
        .first()
    )


def _deliver(ticket_id: int, analysis_id: Optional[int]) -> Dict[str, Any]:
    """在锁内完成一次通知尝试，并落库最终状态。"""
    db = SessionLocal()
    try:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise NotifyNotAllowed("工单不存在")
        analysis = db.get(Analysis, analysis_id) if analysis_id else None
        if not analysis:
            analysis = (
                db.query(Analysis)
                .filter(Analysis.ticket_id == ticket_id)
                .order_by(Analysis.id.desc())
                .first()
            )
        if not analysis:
            raise NotifyNotAllowed("工单尚无分析结果，不能发送通知")

        body = {
            "msg_type": "text",
            "content": {"text": _build_text(ticket, analysis)},
        }

        row = Notification(
            ticket_id=ticket_id,
            analysis_id=analysis.id,
            status="sending",
            request_body=json.dumps(body, ensure_ascii=False),
            created_at=now_iso(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        try:
            response = httpx.post(
                settings.notify_url,
                json=body,
                timeout=settings.notify_timeout,
                trust_env=False,
            )
            row.http_status = response.status_code
            row.response_body = (response.text or "")[:2000]

            if 200 <= response.status_code < 300:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                if isinstance(payload, dict) and payload.get("code", 0) == 0:
                    row.status = "success"
                else:
                    row.status = "failed"
                    row.error = "通知服务返回业务错误"
            else:
                row.status = "failed"
                row.error = f"通知服务返回 HTTP {response.status_code}"
        except httpx.TimeoutException:
            # 超时无法确认对端是否已收到，按“结果未知”处理，不能算成功
            row.status = "unknown"
            row.error = "请求超时，结果未知"
        except httpx.HTTPError as exc:
            row.status = "failed"
            row.error = f"请求失败：{exc}"
        except Exception as exc:  # noqa: BLE001
            row.status = "failed"
            row.error = f"发送异常：{exc}"

        row.finished_at = now_iso()
        db.commit()
        db.refresh(row)
        return notification_to_dict(row)
    finally:
        db.close()


def auto_notify_if_needed(ticket_id: int, analysis_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """高优先级工单的自动通知。

    规则：该工单从未有过任何通知记录时才自动发送。
    一旦存在记录（成功/失败/未知），后续重新分析不自动发送，只能由管理员手动重试，
    以保证“已成功的通知不重复发送”。
    """
    with _notify_lock:
        db = SessionLocal()
        try:
            if _has_success(db, ticket_id):
                return None
            exists = (
                db.query(Notification)
                .filter(Notification.ticket_id == ticket_id)
                .count()
            )
            if exists > 0:
                return None
        finally:
            db.close()
        try:
            return _deliver(ticket_id, analysis_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("自动通知失败 ticket=%s: %s", ticket_id, exc)
            return None


def retry_notification(ticket_id: int) -> Dict[str, Any]:
    """管理员手动重试：仅允许最近一次为 failed/unknown，且从未成功过。"""
    with _notify_lock:
        db = SessionLocal()
        try:
            if _has_success(db, ticket_id):
                raise NotifyNotAllowed("该工单通知已成功发送，不允许重复发送")
            latest = _latest(db, ticket_id)
            if latest is None:
                raise NotifyNotAllowed("该工单尚未发送过通知，无需重试")
            if latest.status == "sending":
                raise NotifyNotAllowed("通知正在发送中，请稍后再试")
            if latest.status not in ("failed", "unknown"):
                raise NotifyNotAllowed("当前通知状态不允许重试")
            analysis_id = latest.analysis_id
        finally:
            db.close()
        return _deliver(ticket_id, analysis_id)
