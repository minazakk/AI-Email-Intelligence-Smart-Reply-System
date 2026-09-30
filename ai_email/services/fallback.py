"""Deterministic, input-derived fallback analysis.

Used only when a live provider fails AND ``AI_ALLOW_FALLBACK=true``. Every
result is marked ``processing_status="partial"`` and ``fallback_used=True``
so it can never be mistaken for a completed AI analysis.
"""

from __future__ import annotations

from typing import Any

from ..providers.mock_heuristics import mock_analysis
from ..schemas import EmailAnalysis, ProcessingMetadata, ProcessingStatus


def deterministic_analysis(payload: dict[str, Any], *, provider_name: str, error: Exception) -> EmailAnalysis:
    data = dict(mock_analysis(payload))
    data.pop("processing_metadata", None)
    analysis = EmailAnalysis.model_validate(data)
    return analysis.model_copy(
        update={
            "processing_metadata": ProcessingMetadata(
                provider=provider_name,
                model="deterministic-rules",
                prompt_version="n/a",
                processing_status=ProcessingStatus.PARTIAL,
                fallback_used=True,
                error=f"{type(error).__name__}: {error}"[:500],
            )
        }
    )


__all__ = ["deterministic_analysis"]
