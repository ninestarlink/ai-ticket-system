import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    """运行期配置，全部来自环境变量；测试中可直接覆盖属性。"""

    def __init__(self) -> None:
        self.model_base_url = os.getenv(
            "MODEL_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
        )
        self.model_api_key = os.getenv("MODEL_API_KEY", "")
        self.model_name = os.getenv("MODEL_NAME", "glm-5.3-flash")
        self.model_timeout = float(os.getenv("MODEL_TIMEOUT_SECONDS", "60"))
        self.notify_url = os.getenv(
            "FEISHU_WEBHOOK_URL", "http://mock-feishu:9000/webhook"
        )
        self.notify_timeout = float(os.getenv("NOTIFY_TIMEOUT_SECONDS", "10"))
        self.database_url = os.getenv(
            "DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'tickets.db'}"
        )


settings = Settings()
