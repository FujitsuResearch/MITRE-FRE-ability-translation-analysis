"""D3FEND ontology data fetching."""

import httpx

from ..logger import get_logger

logger = get_logger("d3fend.client")

D3FEND_ARTIFACTS_URL = "https://d3fend.mitre.org/api/dao/artifacts.json"
D3FEND_TECHNIQUES_URL = "https://d3fend.mitre.org/api/technique/all.json"

# Module-level caches
_artifact_classes: list[str] | None = None
_defensive_techniques: list[str] | None = None


def get_artifact_classes() -> list[str]:
    """Fetch all valid D3FEND artifact class names.

    Returns cached data if already fetched.

    Returns:
        List of artifact class names (e.g., ["Process", "File", "WindowsRegistryKey", ...])

    Raises:
        RuntimeError: If D3FEND API is unavailable
    """
    global _artifact_classes
    if _artifact_classes is not None:
        return _artifact_classes

    logger.info("Fetching D3FEND artifact classes...")
    response = httpx.get(D3FEND_ARTIFACTS_URL, timeout=30.0)
    response.raise_for_status()
    data = response.json()

    _artifact_classes = _extract_artifact_names(data)
    logger.debug(f"Loaded {len(_artifact_classes)} artifact classes")
    return _artifact_classes


def get_defensive_techniques() -> list[str]:
    """Fetch all valid D3FEND defensive technique names.

    Returns cached data if already fetched.

    Returns:
        List of defensive technique names (e.g., ["ProcessMonitoring", "FileAnalysis", ...])

    Raises:
        RuntimeError: If D3FEND API is unavailable
    """
    global _defensive_techniques
    if _defensive_techniques is not None:
        return _defensive_techniques

    logger.info("Fetching D3FEND defensive techniques...")
    response = httpx.get(D3FEND_TECHNIQUES_URL, timeout=30.0)
    response.raise_for_status()
    data = response.json()

    _defensive_techniques = _extract_technique_names(data)
    logger.debug(f"Loaded {len(_defensive_techniques)} defensive techniques")
    return _defensive_techniques


def _extract_artifact_names(data: dict) -> list[str]:
    """Extract artifact class names from D3FEND API response."""
    artifacts = []

    graph = data.get("@graph", [])
    for item in graph:
        artifact_id = item.get("@id", "")
        if artifact_id.startswith("d3f:"):
            class_name = artifact_id[4:]
            artifacts.append(class_name)

    return sorted(set(artifacts))


def _extract_technique_names(data: dict) -> list[str]:
    """Extract defensive technique names from D3FEND API response."""
    techniques = []

    graph = data.get("@graph", [])
    for item in graph:
        label = item.get("rdfs:label", "")
        if label:
            class_name = label.replace(" ", "")
            techniques.append(class_name)

        tech_id = item.get("@id", "")
        if tech_id.startswith("d3f:"):
            class_name = tech_id[4:]
            techniques.append(class_name)

    return sorted(set(techniques))
