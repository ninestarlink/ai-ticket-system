from app.database import SessionLocal
from app.mock_data import execute_tool
from app.models import Ticket
from fakes import (
    HIGH_DUPLICATE,
    LOW_CONSULT,
    MEDIUM_SINGLE_PAYMENT,
    final,
    tool_call,
)


def _create(client, description, token):
    response = client.post(
        "/api/tickets",
        json={
            "name": "李四",
            "email": "lisi@example.com",
            "description": description,
            "submission_token": token,
        },
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        ticket = (
            db.query(Ticket)
            .filter(Ticket.ticket_no == response.json()["ticket_no"])
            .first()
        )
        return ticket.id, ticket.ticket_no


def _detail(client, ticket_id):
    response = client.get(f"/api/admin/tickets/{ticket_id}")
    assert response.status_code == 200
    return response.json()


def test_low_priority_routed_without_notification(client, fake_llm, notify_server):
    fake_llm.responses = [LOW_CONSULT]
    ticket_id, _ = _create(client, "批量采购有优惠吗？", "token-low")

    detail = _detail(client, ticket_id)
    assert detail["analysis_state"] == "success"
    assert detail["analysis"]["category"] == "其他"
    assert detail["analysis"]["priority"] == "低"
    assert detail["department"] == "客服组"
    assert detail["assignee"] == "王琳"
    assert detail["notifications"] == []
    assert notify_server.messages == []


def test_duplicate_charge_high_and_never_resend(client, fake_llm, notify_server):
    fake_llm.responses = [
        tool_call("query_payment", "A1002"),
        HIGH_DUPLICATE,
        tool_call("query_payment", "A1002"),
        HIGH_DUPLICATE,
    ]
    ticket_id, ticket_no = _create(
        client, "订单A1002被扣款两次，请核实", "token-high"
    )

    detail = _detail(client, ticket_id)
    assert detail["order_id"] == "A1002"
    assert detail["order_id_source"] == "description"
    assert detail["analysis"]["priority"] == "高"
    assert detail["department"] == "售后组"
    assert detail["assignee"] == "李静"

    tool_calls = detail["analysis"]["tool_calls"]
    assert tool_calls and tool_calls[0]["name"] == "query_payment"
    assert tool_calls[0]["arguments"]["order_id"] == "A1002"
    assert tool_calls[0]["result"]["count"] == 2

    assert len(detail["notifications"]) == 1
    assert detail["notifications"][0]["status"] == "success"
    assert len(notify_server.messages) == 1

    text = notify_server.messages[0]["content"]["text"]
    assert ticket_no in text
    assert "高" in text
    assert "售后组" in text
    assert "李静" in text

    # 重新分析后仍为高优先级，但已成功的通知不能重复发送
    response = client.post(f"/api/admin/tickets/{ticket_id}/analyze")
    assert response.status_code == 200

    detail = _detail(client, ticket_id)
    assert len(detail["notifications"]) == 1
    assert len(notify_server.messages) == 1


def test_single_payment_not_high(client, fake_llm, notify_server):
    fake_llm.responses = [
        tool_call("query_payment", "A1001"),
        MEDIUM_SINGLE_PAYMENT,
    ]
    ticket_id, _ = _create(client, "A1001 好像被扣了两次钱", "token-single")

    detail = _detail(client, ticket_id)
    assert detail["analysis"]["priority"] == "中"
    assert detail["notifications"] == []
    assert notify_server.messages == []


def test_verified_duplicate_payment_guard(client, fake_llm, notify_server):
    """工具已核实两笔成功支付时，即使模型误判为中，也按题目规则校正为高。"""
    fake_llm.responses = [
        tool_call("query_payment", "A1002"),
        final(
            "支付与退款",
            "中",
            "订单 A1002 存在两笔成功支付",
            "建议人工核实支付记录。",
        ),
    ]
    ticket_id, _ = _create(client, "订单 A1002 被扣款两次", "token-guard")

    detail = _detail(client, ticket_id)
    assert detail["analysis"]["priority"] == "高"
    assert detail["department"] == "售后组"
    assert len(detail["notifications"]) == 1
    assert len(notify_server.messages) == 1


def test_notification_failure_then_manual_retry(client, fake_llm, notify_server):
    notify_server.mode = "fail"
    fake_llm.responses = [tool_call("query_payment", "A1002"), HIGH_DUPLICATE]
    ticket_id, _ = _create(client, "订单 A1002 被扣款两次", "token-fail")

    detail = _detail(client, ticket_id)
    assert detail["notifications"][0]["status"] == "failed"
    assert "HTTP 500" in detail["notifications"][0]["error"]
    assert notify_server.messages == []

    notify_server.mode = "ok"
    response = client.post(f"/api/admin/tickets/{ticket_id}/notify/retry")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert len(notify_server.messages) == 1

    detail = _detail(client, ticket_id)
    assert len(detail["notifications"]) == 2
    # 已成功，不允许再次重试
    again = client.post(f"/api/admin/tickets/{ticket_id}/notify/retry")
    assert again.status_code == 409


def test_notification_timeout_is_unknown_and_not_auto_resent(
    client, fake_llm, notify_server
):
    notify_server.mode = "timeout"
    fake_llm.responses = [
        tool_call("query_payment", "A1002"),
        HIGH_DUPLICATE,
        tool_call("query_payment", "A1002"),
        HIGH_DUPLICATE,
    ]
    ticket_id, _ = _create(client, "订单 A1002 重复扣款", "token-timeout")

    detail = _detail(client, ticket_id)
    assert detail["notifications"][0]["status"] == "unknown"
    assert "未知" in detail["notifications"][0]["error"]
    assert len(notify_server.messages) == 1

    response = client.post(f"/api/admin/tickets/{ticket_id}/analyze")
    assert response.status_code == 200

    detail = _detail(client, ticket_id)
    assert len(detail["notifications"]) == 1
    assert detail["notifications"][0]["status"] == "unknown"
    assert len(notify_server.messages) == 1


def test_reanalysis_to_high_sends_notification(
    client, fake_llm, notify_server
):
    """低优先级工单重新分析后变为高优先级，应补发一次通知。"""
    fake_llm.responses = [LOW_CONSULT]
    ticket_id, _ = _create(client, "批量采购有优惠吗？", "token-rehigh")

    detail = _detail(client, ticket_id)
    assert detail["analysis"]["priority"] == "低"
    assert detail["notifications"] == []
    assert notify_server.messages == []

    fake_llm.responses = [tool_call("query_payment", "A1002"), HIGH_DUPLICATE]
    response = client.post(f"/api/admin/tickets/{ticket_id}/analyze")
    assert response.status_code == 200

    detail = _detail(client, ticket_id)
    assert detail["analysis"]["priority"] == "高"
    assert len(detail["notifications"]) == 1
    assert detail["notifications"][0]["status"] == "success"
    assert len(notify_server.messages) == 1


def test_mock_catalog_contains_required_orders():
    assert execute_tool("query_order", {"order_id": "A1001"})["order"]["status"] == "已发货"
    assert execute_tool("query_payment", {"order_id": "A1001"})["count"] == 1
    assert execute_tool("query_payment", {"order_id": "A1002"})["count"] == 2
    assert execute_tool("query_order", {"order_id": "A9999"})["exists"] is False


def test_model_failure_keeps_ticket_and_can_reanalyze(client, fake_llm):
    fake_llm.responses = [
        RuntimeError("模型调用失败：连接不可达"),
        tool_call("query_order", "A1001"),
        final(
            "其他",
            "中",
            "咨询订单 A1001 的物流进度",
            "订单 A1001 状态为已发货，建议客服组向客户同步物流进度。",
        ),
    ]
    ticket_id, ticket_no = _create(client, "订单 A1001 什么时候到？", "token-down")

    detail = _detail(client, ticket_id)
    assert detail["analysis_state"] == "failed"
    assert detail["analysis"]["status"] == "failed"
    assert "模型调用失败" in detail["analysis"]["error"]
    assert detail["notifications"] == []

    # 故障恢复后重新分析
    response = client.post(f"/api/admin/tickets/{ticket_id}/analyze")
    assert response.status_code == 200

    detail = _detail(client, ticket_id)
    assert detail["analysis_state"] == "success"
    assert detail["analysis"]["priority"] == "中"
    assert detail["department"] == "客服组"
    assert detail["analysis"]["tool_calls"][0]["name"] == "query_order"

    # 工单始终存在且可被用户查询
    query = client.get(f"/api/tickets/{ticket_no}", params={"email": "lisi@example.com"})
    assert query.status_code == 200
