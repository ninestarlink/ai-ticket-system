import json
from typing import Any, Dict, List, Optional

from .ai_service import CATEGORY_ROUTING
from .models import Analysis, Notification, Ticket, ToolCall
from .notify import notification_to_dict


def _safe_json(text: Optional[str]) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def ticket_summary(ticket: Ticket) -> Dict[str, Any]:
    return {
        "id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "name": ticket.name,
        "email": ticket.email,
        "status": ticket.status,
        "category": ticket.category,
        "priority": ticket.priority,
        "department": ticket.department,
        "assignee": ticket.assignee,
        "analysis_state": ticket.analysis_state,
        "summary": None,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def tool_call_dict(row: ToolCall) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "arguments": _safe_json(row.arguments),
        "result": _safe_json(row.result),
        "ok": row.ok,
        "created_at": row.created_at,
    }


def analysis_dict(row: Analysis, tool_calls: Optional[List[ToolCall]] = None) -> Dict[str, Any]:
    data = {
        "id": row.id,
        "status": row.status,
        "category": row.category,
        "priority": row.priority,
        "summary": row.summary,
        "suggestion": row.suggestion,
        "error": row.error,
        "model": row.model,
        "latency_ms": row.latency_ms,
        "created_at": row.created_at,
        "tool_calls": [tool_call_dict(item) for item in (tool_calls or [])],
    }
    return data


def public_ticket_dict(ticket: Ticket) -> Dict[str, Any]:
    return {
        "ticket_no": ticket.ticket_no,
        "status": ticket.status,
        "public_reply": ticket.public_reply,
        "description": ticket.description,
        "order_id": ticket.order_id,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def admin_ticket_dict(
    ticket: Ticket,
    analyses: List[Analysis],
    tool_calls: List[ToolCall],
    notifications: List[Notification],
) -> Dict[str, Any]:
    latest: Optional[Analysis] = None
    if ticket.current_analysis_id:
        latest = next(
            (item for item in analyses if item.id == ticket.current_analysis_id), None
        )
    if latest is None and analyses:
        latest = analyses[0]

    latest_calls = [item for item in tool_calls if latest and item.analysis_id == latest.id]
    assignees = []
    for _, assignee in CATEGORY_ROUTING.values():
        if assignee not in assignees:
            assignees.append(assignee)
    if ticket.assignee and ticket.assignee not in assignees:
        assignees.append(ticket.assignee)

    return {
        "id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "name": ticket.name,
        "email": ticket.email,
        "description": ticket.description,
        "order_id": ticket.order_id,
        "order_id_source": ticket.order_id_source,
        "status": ticket.status,
        "category": ticket.category,
        "priority": ticket.priority,
        "department": ticket.department,
        "assignee": ticket.assignee,
        "public_reply": ticket.public_reply,
        "analysis_state": ticket.analysis_state,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "assignee_options": assignees,
        "analysis": analysis_dict(latest, latest_calls) if latest else None,
        "analyses": [analysis_dict(item) for item in analyses],
        "notifications": [notification_to_dict(item) for item in notifications],
    }
