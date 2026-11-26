from app.database import SessionLocal
from app.models import Ticket
from fakes import LOW_CONSULT


def _create(client, **overrides):
    payload = {
        "name": "张三",
        "email": "zhangsan@example.com",
        "description": "批量采购有优惠吗？",
        "submission_token": "token-a",
    }
    payload.update(overrides)
    return client.post("/api/tickets", json=payload)


def test_submit_idempotent_and_private_query(client, fake_llm):
    fake_llm.responses = [LOW_CONSULT, LOW_CONSULT]

    first = _create(client)
    assert first.status_code == 200
    ticket_no = first.json()["ticket_no"]
    assert ticket_no.startswith("TK-")

    # 同一个提交令牌（按钮防抖/网络重试）只建一张工单
    second = _create(client)
    assert second.status_code == 200
    assert second.json()["ticket_no"] == ticket_no
    assert second.json()["created"] is False

    # 内容相同但新的一次填写，必须正常建单
    third = _create(client, submission_token="token-b")
    assert third.status_code == 200
    assert third.json()["ticket_no"] != ticket_no

    with SessionLocal() as db:
        assert db.query(Ticket).count() == 2

    ok = client.get(f"/api/tickets/{ticket_no}", params={"email": "zhangsan@example.com"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["ticket_no"] == ticket_no
    # 用户端不能看到 AI 分析内容
    assert "analysis" not in body
    assert "priority" not in body
    assert "category" not in body

    bad = client.get(f"/api/tickets/{ticket_no}", params={"email": "other@example.com"})
    assert bad.status_code == 404
