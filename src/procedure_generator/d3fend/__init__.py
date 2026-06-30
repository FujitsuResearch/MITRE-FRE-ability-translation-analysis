"""D3FEND ontology integration for observable enrichment."""

from .client import get_artifact_classes, get_defensive_techniques
from .validator import (
    ATTACK_ARTIFACT_VERBS,
    TELEMETRY_CLASS_MAP,
    validate_artifact_class,
    validate_relationship_verb,
)

__all__ = [
    "get_artifact_classes",
    "get_defensive_techniques",
    "validate_artifact_class",
    "validate_relationship_verb",
    "ATTACK_ARTIFACT_VERBS",
    "TELEMETRY_CLASS_MAP",
]
