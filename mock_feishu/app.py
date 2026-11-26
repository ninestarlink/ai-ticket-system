import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Mock Feishu Webhook")

_lock = threading.Lock()
_state: Dict[str, Any] = {"mode": "ok", "messages": []}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.get("/health")
def health():
    return {"status": "ok", "mode": _state["mode"], "count": len(_state["messages"])}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid json") from None

    mode = _state["mode"]

    if mode == "fail":
        # 明确失败：不保存，返回 500
        raise HTTPException(status_code=500, detail="mock failure")

    if mode == "timeout":
        # 先保存，再延迟 30 秒返回，模拟“已送达但结果未知”
        with _lock:
            _state["messages"].append(
                {"received_at": _now(), "content": payload}
            )
        await asyncio.sleep(30)
        return {"code": 0, "msg": "success"}

    with _lock:
        _state["messages"].append({"received_at": _now(), "content": payload})
    return {"code": 0, "msg": "success"}


@app.get("/messages")
def messages() -> List[Dict[str, Any]]:
    with _lock:
        return list(_state["messages"])


@app.post("/mode")
async def set_mode(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid json") from None

    mode = payload.get("mode")
    if mode not in ("ok", "fail", "timeout"):
        raise HTTPException(
            status_code=400, detail="mode 只能是 ok / fail / timeout"
        )
    _state["mode"] = mode
    return {"mode": mode}


@app.delete("/messages")
def clear_messages():
    """非必需接口，便于本地反复验收。"""
    with _lock:
        _state["messages"] = []
    return {"cleared": True}
