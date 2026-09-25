from functools import lru_cache

from hop_core.app_factory import create_hop_app
from hop_core.credentials import AI_PROVIDER_TYPES, register_builtin_types

from settings import DemoSettings


@lru_cache
def get_settings() -> DemoSettings:
    return DemoSettings()


# The credential types this app offers. An app registers the subset that makes
# sense for it; these three are what the Release Notes Agent uses. Registering
# a type is what puts it in the credentials UI, and the AI provider types are
# additionally what an agent's model configuration is selected from.
register_builtin_types("jira", "heretto", *AI_PROVIDER_TYPES)


app = create_hop_app(
    settings_factory=get_settings,
    title="Hop Demo",
    description="hop-core demo — built-in auth, account, credential, agent, and admin interfaces",
    version="0.1.0",
    # POST /dita/render, behind <hop-dita-content [dita]> on the DITA rendering page.
    include_dita_router=True,
)
