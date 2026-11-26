import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import SessionLocal, init_db
from .models import Ticket
from .routers import admin, public

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 容器重启时，把上次中断在“分析中”的工单标记为失败，允许管理员重新分析
    with SessionLocal() as db:
        db.query(Ticket).filter(Ticket.analysis_state == "running").update(
            {"analysis_state": "failed"}
        )
        db.commit()
    yield


app = FastAPI(title="AI Ticket 智能工单系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(public.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
