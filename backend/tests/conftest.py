import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP_DIR = tempfile.mkdtemp(prefix="ai-ticket-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DIR}/test.db"
os.environ["MODEL_API_KEY"] = "test-key"
os.environ["MODEL_NAME"] = "test-model"
os.environ["MODEL_BASE_URL"] = "http://127.0.0.1:1/v1"
os.environ["FEISHU_WEBHOOK_URL"] = "http://127.0.0.1:1/webhook"
os.environ["NOTIFY_TIMEOUT_SECONDS"] = "1"

import pytest
from fastapi.testclient import TestClient

from app import ai_service
from app.config import settings
from app.database import Base, engine
from app.main import app


class FakeLLM:
    responses = []


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fake_llm(monkeypatch):
    FakeLLM.responses = []

    def fake_chat(self, messages, tools=None):
        if not FakeLLM.responses:
            raise ai_service.LLMError("测试未提供模型响应")
        item = FakeLLM.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(ai_service.LLMClient, "chat", fake_chat)
    return FakeLLM


class NotifyState:
    def __init__(self):
        self.mode = "ok"
        self.messages = []


class NotifyHandler(BaseHTTPRequestHandler):
    state = None

    def log_message(self, *args):  # noqa: D401
        return

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _path(self):
        # 兼容部分客户端发送 absolute-form 请求行（http://host/path）
        path = self.path
        if path.startswith("http://") or path.startswith("https://"):
            from urllib.parse import urlparse

            path = urlparse(path).path
        return path

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            payload = {}

        path = self._path()
        if path == "/webhook":
            if self.state.mode == "fail":
                self._send(500, {"code": 500, "msg": "mock failure"})
                return
            self.state.messages.append(payload)
            if self.state.mode == "timeout":
                time.sleep(2)
            self._send(200, {"code": 0, "msg": "success"})
            return

        if path == "/mode":
            self.state.mode = payload.get("mode", "ok")
            self._send(200, {"mode": self.state.mode})
            return

        self._send(404, {"code": 404})

    def do_GET(self):  # noqa: N802
        if self._path() == "/messages":
            self._send(200, self.state.messages)
            return
        self._send(404, {"code": 404})


@pytest.fixture
def notify_server(monkeypatch):
    state = NotifyState()
    handler = type("Handler", (NotifyHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    monkeypatch.setattr(
        settings, "notify_url", f"http://127.0.0.1:{server.server_port}/webhook"
    )
    monkeypatch.setattr(settings, "notify_timeout", 0.5)

    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
