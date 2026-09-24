"""DITA 1.3 validation, AI-driven correction, and HTML rendering.

Requires the ``dita`` extra: ``pip install 'hop-core[dita]'`` (lxml). DTD
validation additionally uses the ``xmllint`` binary when present on PATH
(``apt-get install libxml2-utils`` / ``brew install libxml2``) and falls back
to structural validation otherwise.
"""

from hop_core.dita.ai import GenerationRequest, GenerationResult, SupportsGenerate
from hop_core.dita.correction import DitaCorrectionService
from hop_core.dita.renderer import (
    DitaParseError,
    DitaRenderer,
    KeyDefinition,
    RenderedTopic,
    exclusions_from_ditaval,
    keys_from_map,
    render_dita,
)
from hop_core.dita.validator import DitaValidator

__all__ = [
    "DitaValidator",
    "DitaCorrectionService",
    "DitaRenderer",
    "DitaParseError",
    "KeyDefinition",
    "RenderedTopic",
    "render_dita",
    "keys_from_map",
    "exclusions_from_ditaval",
    "GenerationRequest",
    "GenerationResult",
    "SupportsGenerate",
]
