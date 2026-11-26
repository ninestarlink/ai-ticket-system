from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from ..ai_service import trigger_analysis
from ..database import SessionLocal
from ..models import Analysis, Notification, Ticket, ToolCall, now_iso
from ..notify import NotifyNotAllowed, retry_notification
from ..schemas import TicketUpdate
from ..serializers import admin_ticket_dict, ticket_summary

router = APIRouter(prefix="/admin", tags=["admin"])

ALLOWED_STATUS = ("待处理", "处理中", "已解决")


@router.get("/tickets")
def list_tickets(
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    q: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
):
    with SessionLocal() as db:
        query = db.query(Ticket)
        if status:
            query = query.filter(Ticket.status == status)
        if category:
            query = query.filter(Ticket.category == category)
        if priority:
            query = query.filter(Ticket.priority == priority)
        if q:
            keyword = f"%{q.strip()}%"
            query = query.filter(
                (Ticket.ticket_no.like(keyword))
                | (Ticket.name.like(keyword))
                | (Ticket.email.like(keyword))
                | (Ticket.description.like(keyword))
            )
        tickets = query.order_by(Ticket.id.desc()).limit(limit).all()

        analysis_ids = [item.current_analysis_id for item in tickets if item.current_analysis_id]
        summaries = {}
        if analysis_ids:
            rows = db.query(Analysis).filter(Analysis.id.in_(analysis_ids)).all()
            summaries = {row.id: row.summary for row in rows}

        items = []
        for ticket in tickets:
            data = ticket_summary(ticket)
            data["summary"] = summaries.get(ticket.current_analysis_id)
            items.append(data)
        return {"items": items, "total": len(items)}


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int):
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="工单不存在")
        analyses = (
            db.query(Analysis)
            .filter(Analysis.ticket_id == ticket_id)
            .order_by(Analysis.id.desc())
            .limit(20)
            .all()
        )
        tool_calls = (
            db.query(ToolCall)
            .filter(ToolCall.ticket_id == ticket_id)
            .order_by(ToolCall.id.desc())
            .all()
        )
        notifications = (
            db.query(Notification)
            .filter(Notification.ticket_id == ticket_id)
            .order_by(Notification.id.desc())
            .all()
        )
        return admin_ticket_dict(ticket, analyses, tool_calls, notifications)


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: int, payload: TicketUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in ALLOWED_STATUS:
        raise HTTPException(status_code=400, detail="状态只能是：待处理 / 处理中 / 已解决")

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="工单不存在")
        if "status" in changes:
            ticket.status = changes["status"]
        if "assignee" in changes:
            ticket.assignee = (changes["assignee"] or "").strip() or ticket.assignee
        if "public_reply" in changes:
            ticket.public_reply = changes["public_reply"] or ""
        ticket.updated_at = now_iso()
        db.commit()
        db.refresh(ticket)
        return {"id": ticket.id, "status": ticket.status, "assignee": ticket.assignee}


@router.post("/tickets/{ticket_id}/analyze")
def re_analyze(ticket_id: int, background_tasks: BackgroundTasks):
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="工单不存在")
        if ticket.analysis_state == "running":
            raise HTTPException(status_code=409, detail="该工单正在分析中，请稍候")

    if not trigger_analysis(ticket_id, background_tasks):
        raise HTTPException(status_code=409, detail="该工单正在分析中，请稍候")
    return {"queued": True}


@router.post("/tickets/{ticket_id}/notify/retry")
def retry_ticket_notification(ticket_id: int):
    try:
        return retry_notification(ticket_id)
    except NotifyNotAllowed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
