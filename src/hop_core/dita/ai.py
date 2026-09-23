"""Minimal AI-service interface for DITA correction.

The protocol now lives in :mod:`hop_core.ai` so callers outside the optional
``dita`` extra can use it without importing lxml. Re-exported here because
``from hop_core.dita.ai import GenerationRequest`` is a published import path.
"""

from hop_core.ai import GenerationRequest, GenerationResult, SupportsGenerate

__all__ = ["GenerationRequest", "GenerationResult", "SupportsGenerate"]
