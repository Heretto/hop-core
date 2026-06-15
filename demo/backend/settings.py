from pathlib import Path

from hop_core.config import HopCoreSettings

# .env lives one level up at demo/.env, shared with docker-compose.yml
_ENV_FILE = str(Path(__file__).parent.parent / ".env")


class DemoSettings(HopCoreSettings):
    # Redis is declared in the base class but unused; provide a default so the
    # demo runs without Redis in place.
    redis_url: str = "redis://localhost:6379"

    class Config(HopCoreSettings.Config):
        env_file = _ENV_FILE
        case_sensitive = False
        extra = "ignore"
