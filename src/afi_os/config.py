from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Tỷ giá quy ước VND→USD cho mô phỏng hoàn vốn và chi phí/ref.
# Người vận hành chỉnh tay giá trị này khi tỷ giá quy ước thay đổi.
# Không lấy giá trị này từ FX ledger: ledger chỉ đối soát tiền thật ở Trang 4.
PAYBACK_FX_VND_PER_USD = Decimal("26000")
LLM_MODEL = "claude-haiku-4-5"
ADVERTISER_PROVIDER = "SERPAPI"
ADVERTISER_CACHE_DAYS = 7
ADVERTISER_ACTIVE_DAYS = 7
ADVERTISER_GOLDMINE_MIN = 15
ADVERTISER_MONTHLY_QUOTA = 250


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or .env."""

    env: str = "development"
    database_url: str = "sqlite:///./data/afi_os.db"
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"
    terms_evidence_max_age_days: int = 90
    allow_demo_seed: bool = True
    llm_model: str = LLM_MODEL

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AFI_OS_",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def web_root(self) -> Path:
        return self.project_root / "apps" / "web"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
