"""Tier 1 Sigma rule library: loading, partitioning, and the duplicate-key
regression guard for the bug where duplicate `CommandLine|contains` keys were
silently collapsed by PyYAML (dropping detection constraints).
"""

from pathlib import Path

import yaml

from procedure_generator import gbse

SIGMA = Path(gbse.SIGMA_YML)


def test_sigma_file_is_packaged():
    assert SIGMA.is_file(), f"packaged sigma library missing at {SIGMA}"


def test_load_sigma_rules_partitions_and_counts():
    lin, win = gbse.load_sigma_rules(SIGMA)
    # Regression guard on the shipped library. If rules are intentionally
    # added/removed, update these numbers in the same commit.
    assert len(lin) == 19, f"expected 19 Linux rules, got {len(lin)}"
    assert len(win) == 30, f"expected 30 Windows rules, got {len(win)}"
    assert len(lin) + len(win) == 49


def test_loaded_rules_have_expected_fields():
    lin, win = gbse.load_sigma_rules(SIGMA)
    for rule in lin + win:
        for key in ("rule_id", "title", "logsource", "tags", "tel"):
            assert key in rule, f"rule missing {key!r}: {rule}"


def test_sigma_has_no_duplicate_mapping_keys():
    """The original bug: a Sigma rule defined `CommandLine|contains` twice, and
    yaml.safe_load silently kept only the last, dropping a detection constraint.
    safe_load won't surface that, so walk the node tree and flag any duplicate
    key within a mapping. Zero duplicates is the invariant.
    """
    dupes = []

    def walk(node, path="doc"):
        if isinstance(node, yaml.MappingNode):
            seen = set()
            for key_node, val_node in node.value:
                if isinstance(key_node, yaml.ScalarNode):
                    if key_node.value in seen:
                        dupes.append(f"{path}.{key_node.value}")
                    seen.add(key_node.value)
                child = getattr(key_node, "value", "?")
                walk(val_node, f"{path}.{child}")
        elif isinstance(node, yaml.SequenceNode):
            for i, item in enumerate(node.value):
                walk(item, f"{path}[{i}]")

    with open(SIGMA, encoding="utf-8") as f:
        for doc in yaml.compose_all(f):
            if doc is not None:
                walk(doc)

    assert not dupes, f"duplicate YAML keys reintroduced: {dupes}"
