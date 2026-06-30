"""Tier 2 GBSE evaluation measures (the compute_auto check battery), the
m0..m3 match relations, and the bipartite graph-edit-distance. README worked
examples are encoded directly as assertions where they exist.
"""

from procedure_generator import gbse


def step(
    step_id,
    tech,
    *,
    parent=None,
    tactic=("Discovery",),
    tel=("process",),
    priv="user",
    sigma=(),
):
    """Build a minimal GBSE step dict with the keys the measures read."""
    return {
        "step_id": step_id,
        "technique_id": tech,
        "parent_technique_id": parent if parent is not None else tech.split(".")[0],
        "tactic": list(tactic),
        "telemetry_classes": list(tel),
        "execution_level": priv,
        "sigma_rules": [{"logsource": s} for s in sigma],
    }


# ===================== compute_auto: per-measure behaviour ==================== #
def test_missing_steps_readme_example():
    # README: control [1..5] vs variant [1,2,4,5] -> step 3 missing -> FAIL.
    g_c = [step(i, "T1059") for i in (1, 2, 3, 4, 5)]
    g_v = [step(i, "T1059") for i in (1, 2, 4, 5)]
    checks, *_ = gbse.compute_auto(g_c, g_v, os_violations=[])
    assert checks["missing_steps"][0] is False
    assert "1 missing" in checks["missing_steps"][1]


def test_extra_steps_flagged():
    g_c = [step(i, "T1059") for i in (1, 2)]
    g_v = [step(i, "T1059") for i in (1, 2, 3)]
    checks, *_ = gbse.compute_auto(g_c, g_v, [])
    assert checks["extra_steps"][0] is False
    assert "1 extra" in checks["extra_steps"][1]


def test_os_constructs_valid_pass_and_fail():
    g = [step(1, "T1059")]
    ok, _ = gbse.compute_auto(g, g, os_violations=[])[0]["os_constructs_valid"]
    bad, _ = gbse.compute_auto(g, g, os_violations=["wine foo.exe"])[0]["os_constructs_valid"]
    assert ok is True
    assert bad is False


def test_technique_match_pass_and_fail():
    g_c = [step(1, "T1059"), step(2, "T1021.001")]
    checks_ok, *_ = gbse.compute_auto(g_c, g_c, [])
    assert checks_ok["technique_ids_match"][0] is True
    assert checks_ok["technique_sequence_match"][0] is True

    g_v = [step(1, "T1059"), step(2, "T1003")]
    checks_bad, *_ = gbse.compute_auto(g_c, g_v, [])
    assert checks_bad["technique_ids_match"][0] is False
    assert "1 mismatches" in checks_bad["technique_ids_match"][1]


def test_parent_technique_match():
    g_c = [step(1, "T1021.001", parent="T1021")]
    ok = gbse.compute_auto(g_c, g_c, [])[0]["parent_technique_ids_match"][0]
    bad = gbse.compute_auto(g_c, [step(1, "T1021.001", parent="T1059")], [])[0][
        "parent_technique_ids_match"
    ][0]
    assert ok is True
    assert bad is False


def test_telemetry_classes_match_strict_threshold():
    # Overlap of exactly 0.5 must FAIL (strict '>'): {file,process} vs {other,process}.
    g_c = [step(1, "T1562.001", tel=("file", "process"))]
    g_v = [step(1, "T1562.001", tel=("other", "process"))]
    passed, _ = gbse.telemetry_classes_match(g_c, g_v)
    assert passed is False
    # identical telemetry passes.
    assert gbse.telemetry_classes_match(g_c, g_c)[0] is True


def test_extra_telemetry_classes():
    g = [step(1, "T1059", tel=("process", "other"))]  # 'other' is not a VALID class
    checks, *_ = gbse.compute_auto(g, g, [])
    assert checks["extra_telemetry_classes"][0] is False
    assert "other" in checks["extra_telemetry_classes"][1]


def test_telemetry_diversity_and_multi_class():
    g_v = [
        step(1, "T1059", tel=("file", "process")),
        step(2, "T1021.001", tel=("network", "process")),
    ]
    checks, *_ = gbse.compute_auto(g_v, g_v, [])
    assert checks["telemetry_diversity"][0] is True  # {file,process,network} = 3
    assert checks["telemetry_multi_class"][0] is True  # 2/2 >= 0.80


def test_telemetry_multi_class_fails_with_singletons():
    g_v = [
        step(1, "T1059", tel=("process",)),
        step(2, "T1021.001", tel=("network",)),
        step(3, "T1003", tel=("file",)),
    ]
    checks, *_ = gbse.compute_auto(g_v, g_v, [])
    assert checks["telemetry_multi_class"][0] is False  # 0/3 < 0.80
    assert checks["telemetry_diversity"][0] is True  # 3 distinct classes


def test_tactic_sequence_match():
    g_c = [step(1, "T1059", tactic=("Execution",))]
    ok = gbse.compute_auto(g_c, g_c, [])[0]["tactic_sequence_match"][0]
    bad = gbse.compute_auto(g_c, [step(1, "T1059", tactic=("Discovery",))], [])[0][
        "tactic_sequence_match"
    ][0]
    assert ok is True
    assert bad is False


def test_privilege_progression_match():
    g_c = [step(1, "T1059", priv="user")]
    ok = gbse.compute_auto(g_c, g_c, [])[0]["privilege_progression_match"][0]
    # npv maps admin/elevated -> 'elevated', user -> 'non-elevated'
    bad = gbse.compute_auto(g_c, [step(1, "T1059", priv="admin")], [])[0][
        "privilege_progression_match"
    ][0]
    assert ok is True
    assert bad is False


def test_compute_auto_aggregate_counts_all_pass():
    g = [
        step(1, "T1059", tel=("file", "process")),
        step(2, "T1021.001", tel=("network", "process")),
    ]
    checks, passed, total, auto = gbse.compute_auto(g, g, [])
    assert total == len(checks) == 12
    assert passed == sum(1 for ok, _ in checks.values() if ok)
    assert auto == round(passed / total, 4)
    # identical control == variant -> every check passes
    assert passed == 12
    assert auto == 1.0


# ============================ match relations m0..m3 ========================= #
def test_m0_technique_identity():
    assert gbse.m0(step(1, "T1059"), step(1, "T1059")) is True
    assert gbse.m0(step(1, "T1059"), step(1, "T1003")) is False


def test_m1_requires_tactic_overlap():
    same = (step(1, "T1059", tactic=("Execution",)), step(1, "T1059", tactic=("Execution",)))
    assert gbse.m1(*same) is True
    # same technique but disjoint tactics -> fail
    assert (
        gbse.m1(step(1, "T1059", tactic=("Execution",)), step(1, "T1059", tactic=("Discovery",)))
        is False
    )
    # different technique -> fail regardless
    assert gbse.m1(step(1, "T1059"), step(1, "T1003")) is False


def test_m2_strict_telemetry_overlap():
    hi = (
        step(1, "T1059", tactic=("Execution",), tel=("file", "process", "network")),
        step(1, "T1059", tactic=("Execution",), tel=("file", "process", "network")),
    )
    assert gbse.m2(*hi) is True
    # overlap exactly 0.5 -> fail (strict '>')
    half = (
        step(1, "T1059", tactic=("Execution",), tel=("file", "process")),
        step(1, "T1059", tactic=("Execution",), tel=("other", "process")),
    )
    assert gbse.m2(*half) is False


def test_m3_independent_uses_sigma_logsource():
    c = step(1, "T1059", sigma=("linux/process_creation",))
    v = step(1, "T1059", sigma=("linux/process_creation",))
    assert gbse.m3_independent(c, v) is True
    # different technique short-circuits via m0
    assert gbse.m3_independent(step(1, "T1059"), step(1, "T1003")) is False


# ============================== bipartite_ged =============================== #
def test_bipartite_ged_identical_is_zero_distance():
    steps = [step(1, "T1059"), step(2, "T1021.001")]
    ged, sim, fails, norm = gbse.bipartite_ged(steps, steps, gbse.m0)
    assert ged == 0.0
    assert sim == 1.0
    assert fails == []
    assert norm == 2


def test_bipartite_ged_one_mismatch():
    c = [step(1, "T1059"), step(2, "T1021.001")]
    v = [step(1, "T1059"), step(2, "T1003")]  # second step differs
    ged, sim, fails, norm = gbse.bipartite_ged(c, v, gbse.m0)
    assert ged == 1.0
    assert sim == 0.5  # 1 - 1/2
    assert len(fails) == 1
    assert fails[0]["ctrl_tech"] != fails[0]["var_tech"]
