from typing import Optional

from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    name: str = Field(..., max_length=50)
    email: str = Field(..., max_length=120)
    description: str = Field(..., max_length=4000)
    order_id: Optional[str] = Field(default=None, max_length=32)
    submission_token: Optional[str] = Field(default=None, max_length=64)


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    assignee: Optional[str] = Field(default=None, max_length=32)
    public_reply: Optional[str] = Field(default=None, max_length=2000)
