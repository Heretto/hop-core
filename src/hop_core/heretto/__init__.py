"""Read-only Heretto CCMS access for agent references.

``HerettoClient`` talks to one instance as one credential's account;
``ReferenceContentSource`` turns a referenced file — a topic, or a map and
every topic it links to — into readable text, through a cache.
"""

from hop_core.heretto.client import HerettoClient, HerettoError, HerettoFile
from hop_core.heretto.content import (
    ReferenceCache,
    ReferenceContent,
    ReferenceContentSource,
    TTLReferenceCache,
    read_file,
)
from hop_core.heretto.text import dita_to_text

__all__ = [
    "HerettoClient",
    "HerettoError",
    "HerettoFile",
    "ReferenceCache",
    "ReferenceContent",
    "ReferenceContentSource",
    "TTLReferenceCache",
    "dita_to_text",
    "read_file",
]
