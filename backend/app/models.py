from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)

from .database import Base


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_no = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    email = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=False)
    order_id = Column(String(32), nullable=True)
    order_id_source = Column(String(16), nullable=True)

    status = Column(String(16), nullable=False, default="待处理")
    department = Column(String(32), nullable=True)
    assignee = Column(String(32), nullable=True)
    public_reply = Column(Text, nullable=False, default="")

    category = Column(String(16), nullable=True)
    priority = Column(String(8), nullable=True)
    analysis_state = Column(String(16), nullable=False, default="none")
    current_analysis_id = Column(Integer, nullable=True)

    submission_token = Column(String(64), unique=True, nullable=False)
    created_at = Column(String(32), nullable=False, default=now_iso)
    updated_at = Column(String(32), nullable=False, default=now_iso)


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, nullable=False, index=True)
    status = Column(String(16), nullable=False, default="running")
    category = Column(String(16), nullable=True)
    priority = Column(String(8), nullable=True)
    summary = Column(Text, nullable=True)
    suggestion = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    raw_output = Column(Text, nullable=True)
    model = Column(String(64), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(String(32), nullable=False, default=now_iso)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, nullable=False, index=True)
    ticket_id = Column(Integer, nullable=False, index=True)
    name = Column(String(32), nullable=False)
    arguments = Column(Text, nullable=False, default="{}")
    result = Column(Text, nullable=False, default="{}")
    ok = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(32), nullable=False, default=now_iso)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, nullable=False, index=True)
    analysis_id = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="sending")
    http_status = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    request_body = Column(Text, nullable=False, default="{}")
    response_body = Column(Text, nullable=True)
    created_at = Column(String(32), nullable=False, default=now_iso)
    finished_at = Column(String(32), nullable=True)
