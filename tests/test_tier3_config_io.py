"""Tier 3 config validation (GBSEConfig.validate / merge) and the
banner-tolerant artifact loader (parse_any). These fail loudly on bad input
rather than deep in a run.
"""

import json

import pytest

from procedure_generator import gbse
from procedure_generator.gbse import GBSEConfig


# =============================== GBSEConfig ================================= #
def test_default_config_is_valid():
    cfg = GBSEConfig().validate()
    assert cfg.ts and cfg.base and cfg.out and cfg.sigma_yml
    assert 0.0 <= cfg.tr <= 1.0


@pytest.mark.parametrize("field", ["ts", "base", "out", "sigma_yml"])
def test_empty_string_fields_rejected(field):
    with pytest.raises(ValueError, match=field):
        GBSEConfig(**{field: ""}).validate()


@pytest.mark.parametrize("field", ["tr", "dv", "dv_i", "gate"])
def test_out_of_range_numeric_rejected(field):
    with pytest.raises(ValueError, match=field):
        GBSEConfig(**{field: 1.5}).validate()


@pytest.mark.parametrize("field", ["tr", "dv", "dv_i", "gate"])
def test_non_numeric_calibration_rejected(field):
    with pytest.raises(ValueError, match=field):
        GBSEConfig(**{field: "high"}).validate()


def test_weights_missing_keys_rejected():
    with pytest.raises(ValueError, match="weights missing"):
        GBSEConfig(weights={"bcf_auto": 0.5}).validate()


def test_weights_non_numeric_rejected():
    bad = {"bcf_auto": 0.5, "bcf_sim": 0.5, "s_bcf": 0.4, "s_tr": 0.3, "s_dv": "x"}
    with pytest.raises(ValueError, match="weights.s_dv"):
        GBSEConfig(weights=bad).validate()


def test_merge_overrides_ignores_none_and_unknown():
    cfg = GBSEConfig().merge({"tr": 0.7, "dv": None, "bogus": 1})
    assert cfg.tr == 0.7
    assert cfg.dv == GBSEConfig().dv  # None is ignored, default preserved


def test_merge_weights_is_partial():
    cfg = GBSEConfig().merge({"weights": {"s_tr": 0.9}})
    assert cfg.weights["s_tr"] == 0.9
    assert cfg.weights["bcf_auto"] == 0.5  # untouched keys preserved


# ================================ parse_any ================================ #
def test_parse_any_plain_json(tmp_path):
    p = tmp_path / "plain.json"
    p.write_text(json.dumps({"a": 1, "b": [1, 2]}))
    assert gbse.parse_any(str(p)) == {"a": 1, "b": [1, 2]}


def test_parse_any_strips_leading_banner(tmp_path):
    p = tmp_path / "banner.json"
    p.write_text("==== REPORT ====\nModel: gpt-4o\n\n" + json.dumps({"ok": True}))
    assert gbse.parse_any(str(p)) == {"ok": True}


def test_parse_any_drops_full_line_comments(tmp_path):
    p = tmp_path / "commented.json"
    p.write_text('{\n  "a": 1,\n// a comment line\n  "b": 2\n}')
    assert gbse.parse_any(str(p)) == {"a": 1, "b": 2}


def test_parse_any_scrubs_control_chars(tmp_path):
    p = tmp_path / "ctrl.json"
    p.write_text('{"a": "x\x07y"}')  # raw BEL inside a string value
    assert gbse.parse_any(str(p)) == {"a": "xy"}


def test_parse_any_no_json_raises(tmp_path):
    p = tmp_path / "nojson.txt"
    p.write_text("just a banner\nno json here\n")
    with pytest.raises(ValueError, match="no JSON"):
        gbse.parse_any(str(p))
