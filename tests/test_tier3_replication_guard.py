"""Tier 3 the replication validate_node guard: an empty/refused procedure
must fail loudly at validation, not propagate an empty action_sequence
downstream. Both cases below use the direct-parse path, so no LLM is called.

The node import pulls in the workflow package (langgraph), so the module is
skipped if those runtime deps are absent.
"""

import json

import pytest

# Importing the node pulls in the workflow package (langgraph + langchain).
# Skip the module cleanly if any of those runtime deps are unavailable, rather
# than erroring at collection.
validate_node = None
try:
    from procedure_generator.workflows.nodes.replication.validate import validate_node
except ImportError:
    pass

pytestmark = pytest.mark.skipif(
    validate_node is None,
    reason="workflow runtime deps (langgraph/langchain) not installed",
)


def _valid_step():
    return {
        "tactic": "Execution",
        "technique_id": "T1059.001",
        "technique_name": "PowerShell",
        "os": "Windows",
        "command": "powershell -enc <...>",
        "description": "run a script",
        "required_privilege": "user",
        "dependencies_constraints": "none",
        "telemetry_expected": "Process creation event",
    }


def test_empty_action_sequence_raises():
    state = {
        "converted_procedure": json.dumps({"action_sequence": []}),
        "model": "gpt-oss:120b",
        "replicated_procedure": "I'm sorry, but I can't help with that.",
    }
    with pytest.raises(ValueError, match="no usable steps"):
        validate_node(state)


def test_valid_procedure_passes_through():
    state = {
        "converted_procedure": json.dumps({"action_sequence": [_valid_step()]}),
        "model": "gpt-4o",
        "replicated_procedure": "<a real reproduced procedure>",
    }
    out = validate_node(state)
    assert len(out["validated_output"]["action_sequence"]) == 1
