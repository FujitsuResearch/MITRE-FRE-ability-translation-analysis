"""D3FEND class validation and fuzzy matching."""

import re
from difflib import SequenceMatcher

from ..logger import get_logger
from .client import get_artifact_classes, get_defensive_techniques

logger = get_logger("d3fend.validator")

# Valid D3FEND relationship verbs for attack step -> artifact edges
ATTACK_ARTIFACT_VERBS = {
    "executes",
    "creates",
    "deletes",
    "accesses",
    "modifies",
    "generates",
    "loads",
    "copies",
    "injects",
    "reads",
    "writes",
}

# Common synonyms that map to valid attack verbs
ATTACK_VERB_SYNONYMS = {
    "runs": "executes",
    "spawns": "executes",
    "launches": "executes",
    "invokes": "executes",
    "starts": "executes",
    "downloads": "loads",
    "fetches": "loads",
    "retrieves": "loads",
    "touches": "accesses",
    "queries": "accesses",
    "opens": "accesses",
    "removes": "deletes",
    "erases": "deletes",
    "updates": "modifies",
    "changes": "modifies",
    "edits": "modifies",
    "produces": "generates",
    "emits": "generates",
    "outputs": "generates",
}

# Map D3FEND artifact classes to simplified telemetry categories
TELEMETRY_CLASS_MAP = {
    # Process telemetry
    "Process": "process",
    "ExecutableBinary": "process",
    "ExecutableScript": "process",
    "Script": "process",
    "Application": "process",
    "SharedLibraryFile": "process",
    # File telemetry
    "File": "file",
    "LogFile": "file",
    "Log": "file",
    "Directory": "file",
    "OperatingSystemConfigurationFile": "file",
    "CommandHistoryLog": "file",
    "EventLog": "file",
    # Network telemetry
    "NetworkTraffic": "network",
    "WebNetworkTraffic": "network",
    "DNSNetworkTraffic": "network",
    "URL": "network",
    "IPAddress": "network",
    "Hostname": "network",
    # Identity/authentication telemetry
    "UserAccount": "identity",
    "Credential": "identity",
    "Password": "identity",
    "KerberosTicket": "identity",
    "Certificate": "identity",
    "Session": "identity",
    # Registry telemetry (Windows-specific)
    "WindowsRegistryKey": "registry",
    "WindowsRegistryValue": "registry",
    # Persistence telemetry
    "ScheduledJob": "persistence",
    "Service": "persistence",
    # IPC telemetry
    "NamedPipe": "ipc",
    # Other
    "Email": "email",
    "Database": "database",
}


def _similarity(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _find_matches(
    invalid_class: str, valid_classes: list[str], threshold: float = 0.6
) -> list[tuple[str, float]]:
    """Find valid classes that match the invalid class name.

    Uses multiple strategies:
    1. Exact substring match
    2. First word match (prioritizes noun)
    3. Shared words with weighting
    4. Sequence similarity for typos

    Returns:
        List of (class_name, score) tuples sorted by score descending
    """
    matches = []
    invalid_lower = invalid_class.lower()

    # Split camelCase into words for better matching
    invalid_words = re.findall(r"[A-Z][a-z]+|[a-z]+", invalid_class)
    invalid_words_lower = [w.lower() for w in invalid_words]

    for valid in valid_classes:
        valid_lower = valid.lower()
        valid_words = re.findall(r"[A-Z][a-z]+|[a-z]+", valid)
        valid_words_lower = [w.lower() for w in valid_words]

        score = 0.0

        # Strategy 1: Exact match
        if invalid_lower == valid_lower:
            score = 1.0

        # Strategy 2: One is substring of the other
        elif invalid_lower in valid_lower or valid_lower in invalid_lower:
            score = 0.85

        # Strategy 3: First word match (noun is usually first, most important)
        elif invalid_words_lower and valid_words_lower:
            if invalid_words_lower[0] == valid_words_lower[0]:
                score = 0.75
                shared = set(invalid_words_lower) & set(valid_words_lower)
                score += len(shared) * 0.05

            else:
                shared = set(invalid_words_lower) & set(valid_words_lower)
                if shared:
                    score = len(shared) / max(len(invalid_words_lower), len(valid_words_lower))
                    score = min(0.7, score + 0.2)

        # Strategy 4: Sequence similarity for typos
        if score < threshold:
            sim = _similarity(invalid_class, valid)
            if sim > score:
                score = sim

        if score >= threshold:
            matches.append((valid, score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:5]


def validate_relationship_verb(
    verb: str,
    verb_type: str = "attack",
) -> tuple[bool, str]:
    """Validate a D3FEND relationship verb.

    Args:
        verb: The relationship verb to validate (e.g., "executes", "analyzes")
        verb_type: Either "attack" (step->artifact) or "defense" (countermeasure->artifact)

    Returns:
        Tuple of (is_valid, corrected_verb)
    """
    valid_verbs = ATTACK_ARTIFACT_VERBS
    synonyms = ATTACK_VERB_SYNONYMS
    verb_lower = verb.lower()

    # Check if already valid
    if verb_lower in valid_verbs:
        return True, verb_lower

    # Check synonyms first (explicit mappings)
    if verb_lower in synonyms:
        mapped = synonyms[verb_lower]
        logger.debug(f"Mapping {verb_type} relationship '{verb}' -> '{mapped}'")
        return False, mapped

    # Find best match using similarity
    best_match = None
    best_score = 0.0

    for valid in valid_verbs:
        score = _similarity(verb_lower, valid)
        if score > best_score:
            best_score = score
            best_match = valid

    if best_match and best_score >= 0.5:
        logger.debug(f"Invalid {verb_type} relationship '{verb}' -> using '{best_match}'")
        return False, best_match

    # Default fallback
    fallback = "accesses"
    logger.debug(f"Invalid {verb_type} relationship '{verb}' -> using fallback '{fallback}'")
    return False, fallback


def validate_artifact_class(d3f_class: str) -> tuple[bool, str, list[str]]:
    """Validate a D3FEND artifact class and suggest corrections.

    Args:
        d3f_class: The class to validate (e.g., "d3f:Process" or "Process")

    Returns:
        Tuple of (is_valid, corrected_class, suggestions)
        - is_valid: True if the class is valid
        - corrected_class: The class to use (original if valid, best match if not)
        - suggestions: List of suggested alternatives if invalid
    """
    # Strip d3f: prefix if present
    class_name = d3f_class[4:] if d3f_class.startswith("d3f:") else d3f_class

    valid_classes = get_artifact_classes()

    # Check if valid
    if class_name in valid_classes:
        return True, class_name, []

    # Find fuzzy matches
    matches = _find_matches(class_name, valid_classes)

    if matches:
        best_match = matches[0][0]
        suggestions = [m[0] for m in matches]
        logger.debug(
            f"Invalid artifact class '{class_name}' -> using '{best_match}' "
            f"(suggestions: {suggestions[:3]})"
        )
        return False, best_match, suggestions

    # No good matches - fall back to generic File or Process
    fallback = "File"
    logger.debug(f"Invalid artifact class '{class_name}' -> using fallback '{fallback}'")
    return False, fallback, []


def validate_defensive_technique(d3f_class: str) -> tuple[bool, str, list[str]]:
    """Validate a D3FEND defensive technique and suggest corrections.

    Args:
        d3f_class: The class to validate (e.g., "d3f:ProcessMonitoring")

    Returns:
        Tuple of (is_valid, corrected_class, suggestions)
    """
    # Strip d3f: prefix if present
    class_name = d3f_class[4:] if d3f_class.startswith("d3f:") else d3f_class

    valid_classes = get_defensive_techniques()

    # Check if valid
    if class_name in valid_classes:
        return True, class_name, []

    # Find fuzzy matches
    matches = _find_matches(class_name, valid_classes)

    if matches:
        best_match = matches[0][0]
        suggestions = [m[0] for m in matches]
        logger.debug(
            f"Invalid defensive technique '{class_name}' -> using '{best_match}' "
            f"(suggestions: {suggestions[:3]})"
        )
        return False, best_match, suggestions

    # No good matches - fall back to ProcessAnalysis
    fallback = "ProcessAnalysis"
    logger.debug(f"Invalid defensive technique '{class_name}' -> using fallback '{fallback}'")
    return False, fallback, []


def get_telemetry_class(artifact_class: str) -> str:
    """Map a D3FEND artifact class to a simplified telemetry category.

    Args:
        artifact_class: D3FEND artifact class (with or without d3f: prefix)

    Returns:
        Telemetry category string (e.g., "process", "file", "network")
    """
    # Strip d3f: prefix if present
    class_name = artifact_class[4:] if artifact_class.startswith("d3f:") else artifact_class

    return TELEMETRY_CLASS_MAP.get(class_name, "other")


def derive_telemetry_classes(observables: list[str]) -> list[str]:
    """Derive unique telemetry classes from a list of D3FEND observables.

    Args:
        observables: List of D3FEND artifact class names

    Returns:
        Sorted list of unique telemetry categories
    """
    telemetry = set()
    for obs in observables:
        telemetry.add(get_telemetry_class(obs))
    return sorted(telemetry)
