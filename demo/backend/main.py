from functools import lru_cache

from hop_core.app_factory import create_hop_app

from settings import DemoSettings


@lru_cache
def get_settings() -> DemoSettings:
    return DemoSettings()


app = create_hop_app(
    settings_factory=get_settings,
    title="Hop Demo",
    description="hop-core demo — built-in auth, account, and admin interfaces",
    version="0.1.0",
)
