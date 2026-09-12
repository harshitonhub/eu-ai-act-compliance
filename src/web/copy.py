"""Presentational copy shared across templates/routers. Not a new legal conclusion --
purely how an existing ClassificationState is glossed in plain language for the UI.
"""

from __future__ import annotations

from schemas.enums import ClassificationState

STATE_EXPLANATIONS: dict[str, str] = {
    ClassificationState.YES.value: "Applies.",
    ClassificationState.NO.value: "Does not apply.",
    ClassificationState.POSSIBLY.value: "Uncertain — human review recommended.",
    ClassificationState.INSUFFICIENT_INFORMATION.value: "Not enough information was provided to determine this.",
    ClassificationState.NOT_APPLICABLE.value: "This requirement isn't in force yet as of the assessment date.",
}
