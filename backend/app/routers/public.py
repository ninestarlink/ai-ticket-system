import re
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy.orm import Session

from ..ai_service import trigger_analysis
from ..database import SessionLocal
from ..models import Ticket, now_iso
from ..schemas import TicketCreate
from ..serializers import public_ticket_dict

router = APIRouter(prefix="/tickets", tags=["public"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# 订单号可能直接粘在中文里（如“订单A1002被扣款”），不能用 \b
ORDER_RE = re.compile(r"(?<![A-Za-z0-9])A\d{4}(?![A-Za-z0-9])", re.IGNORECASE)


def _normalize_order(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip().upper()
    return text or None


def _extract_order(description: str) -> Optional[str]:
    match = ORDER_RE.search(description or "")
    return match.group(0).upper() if match else None


def _generate_ticket_no(db: Session) -> str:
    for _ in range(10):
        candidate = (
            "TK-"
            + datetime.now().strftime("%y%m%d")
            + "-"
            + secrets.token_hex(3).upper()
        )
        exists = db.query(Ticket.id).filter(Ticket.ticket_no == candidate).first()
        if not exists:
            return candidate
    raise RuntimeError("工单号生成失败")


@router.post("")
def create_ticket(payload: TicketCreate, background_tasks: BackgroundTasks):
    name = (payload.name or "").strip()
    email = (payload.email or "").strip().lower()
    description = (payload.description or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="请填写姓名")
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if len(description) < 2:
        raise HTTPException(status_code=400, detail="问题描述太短")

    token = (payload.submission_token or "").strip() or secrets.token_hex(16)

    with SessionLocal() as db:
        existing = (
            db.query(Ticket).filter(Ticket.submission_token == token).first()
        )
        if existing:
            return {
                "ticket_no": existing.ticket_no,
                "status": existing.status,
                "created": False,
            }

        order_id = _normalize_order(payload.order_id)
        source = "field" if order_id else None
        if not order_id:
            order_id = _extract_order(description)
            source = "description" if order_id else None

        ticket = Ticket(
            ticket_no=_generate_ticket_no(db),
            name=name,
            email=email,
            description=description,
            order_id=order_id,
            order_id_source=source,
            status="待处理",
            public_reply="",
            analysis_state="none",
            submission_token=token,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        ticket_id = ticket.id
        ticket_no = ticket.ticket_no

    trigger_analysis(ticket_id, background_tasks)
    return {"ticket_no": ticket_no, "status": "待处理", "created": True}


@router.get("/{ticket_no}")
def query_ticket(ticket_no: str, email: str = Query(..., max_length=120)):
    """必须工单号 + 提交邮箱同时匹配，否则统一返回查不到。"""
    normalized_email = (email or "").strip().lower()
    with SessionLocal() as db:
        ticket = (
            db.query(Ticket)
            .filter(
                Ticket.ticket_no == ticket_no.strip().upper(),
                Ticket.email == normalized_email,
            )
            .first()
        )
        if not ticket:
            raise HTTPException(status_code=404, detail="工单编号或邮箱不正确")
        return public_ticket_dict(ticket)
