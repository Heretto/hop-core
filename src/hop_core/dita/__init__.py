"""DITA 1.3 validation and AI-driven correction.

Requires the ``dita`` extra: ``pip install 'hop-core[dita]'`` (lxml). DTD
validation additionally uses the ``xmllint`` binary when present on PATH
(``apt-get install libxml2-utils`` / ``brew install libxml2``) and falls back
to structural validation otherwise.
"""

from hop_core.dita.ai import GenerationRequest, GenerationResult, SupportsGenerate
from hop_core.dita.correction import DitaCorrectionService
from hop_core.dita.validator import DitaValidator

__all__ = [
    "DitaValidator",
    "DitaCorrectionService",
    "GenerationRequest",
    "GenerationResult",
    "SupportsGenerate",
]
