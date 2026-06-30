"""Graph-Based Structural Evaluation (GBSE) of LLM-translated procedures.

Consumes the artifacts emitted by the procedure_generator pipeline (the
``full``/``evaluate`` stages) for a single run and scores cross-OS structural
fidelity: a normalized graph-edit distance across technique/tactic/telemetry/
Sigma-logsource layers, the automated check battery, composite scores against
the CALDERA deployment gate, and the gold-control technique divergence.

Integrates as the ``gbse`` subcommand of the ``procedure-generator`` CLI; see
``add_gbse_subparser``/``run_gbse``. Calibration inputs (TR, DV, gate, weights)
resolve from defaults < data/gbse_config.json < CLI flags.
"""

import argparse
import copy
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from glob import glob
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

try:
    import yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from procedure_generator.logger import ProcedureLogger

logger = ProcedureLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults for the recorded reference run. These remain the built-in fallback;
# a gbse_config.json in the data/ directory and/or CLI flags override them. The
# run timestamp is normally auto-detected from the input directory; the pinned
# default below only applies when detection finds nothing.
# ---------------------------------------------------------------------------
TS = "1774278112.367423"
BASE = "Input"
OUT = "output"
SIGMA_YML = str(Path(__file__).parent / "data" / "sigma_rules_gbse.yml")

INF = 1e9  # bipartite cost-matrix sentinel (algorithmic, not calibration)

# Manual-evaluation inputs and composite-scoring calibration. Analytic settings
# pending empirical calibration (paper Sec 3.7 / 6.3); exposed via config so the
# TR/DV/gate/weight sensitivity analysis can be run without editing source.
TR = 0.43
DV = 0.51
DV_I = 0.65
GATE = 0.80
WEIGHTS = {"bcf_auto": 0.5, "bcf_sim": 0.5, "s_bcf": 0.4, "s_tr": 0.3, "s_dv": 0.3}

# Input artifacts required under the base directory, keyed by the {ts} timestamp.
INPUT_FILES = (
    "input_procedure",
    "full_output",
    "conversion_result",
    "evaluation_result",
    "os_violations",
)


@dataclass
class GBSEConfig:
    """Resolved run configuration. Field defaults are the recorded-run
    constants above, so an un-overridden config reproduces it."""

    ts: str = TS
    base: str = BASE
    out: str = OUT
    sigma_yml: str = SIGMA_YML
    tr: float = TR
    dv: float = DV
    dv_i: float = DV_I
    gate: float = GATE
    weights: dict = field(default_factory=lambda: dict(WEIGHTS))

    def merge(self, d: dict) -> "GBSEConfig":
        """Override fields from a dict (config file or CLI), ignoring None/absent."""
        for k, v in (d or {}).items():
            if v is None:
                continue
            if k == "weights" and isinstance(v, dict):
                self.weights = {**self.weights, **v}
            elif hasattr(self, k):
                setattr(self, k, v)
            else:
                logger.warning(f"Unknown config key ignored: {k}")
        return self

    def validate(self) -> "GBSEConfig":
        """Fail loudly on a malformed config rather than deep in the run."""
        for k in ("ts", "base", "out", "sigma_yml"):
            if not isinstance(getattr(self, k), str) or not getattr(self, k):
                raise ValueError(f"config.{k} must be a non-empty string")
        for k in ("tr", "dv", "dv_i", "gate"):
            v = getattr(self, k)
            if not isinstance(v, int | float) or not (0.0 <= float(v) <= 1.0):
                raise ValueError(f"config.{k} must be a number in [0, 1] (got {v!r})")
        req = {"bcf_auto", "bcf_sim", "s_bcf", "s_tr", "s_dv"}
        missing = req - set(self.weights)
        if missing:
            raise ValueError(f"config.weights missing keys: {sorted(missing)}")
        for k, v in self.weights.items():
            if not isinstance(v, int | float):
                raise ValueError(f"config.weights.{k} must be numeric (got {v!r})")
        return self


def _detect_timestamp(base: str) -> str | None:
    """Infer the run timestamp from input_procedure_<ts>.json under ``base``."""
    cands = sorted(glob(os.path.join(base, "input_procedure_*.json")))
    if not cands:
        return None
    m = re.search(r"input_procedure_(.+)\.json$", os.path.basename(cands[-1]))
    return m.group(1) if m else None


def add_gbse_subparser(subparsers) -> "argparse.ArgumentParser":
    """Register the ``gbse`` subcommand on the project CLI's subparsers.

    In cli.py::main, call ``add_gbse_subparser(subparsers)`` alongside the other
    parsers, then dispatch ``args.command == "gbse"`` to ``run_gbse(args, logger)``.
    """
    p = subparsers.add_parser(
        "gbse",
        help="Graph-based structural evaluation of a translated procedure run",
    )
    p.add_argument(
        "input",
        help="Pipeline output directory (or output.zip) holding the run artifacts",
    )
    p.add_argument(
        "--timestamp",
        help="Run timestamp; auto-detected from the input directory if omitted",
    )
    p.add_argument("--config", help="Path to a gbse JSON config file (calibration overrides)")
    p.add_argument("--sigma", dest="sigma_yml", help="Path to the Sigma rule library")
    p.add_argument("--tr", type=float, help="Technical Realism (manual)")
    p.add_argument("--dv", type=float, help="Defensive Value (manual)")
    p.add_argument("--dv-i", dest="dv_i", type=float, help="Defensive Value for independent-L3")
    p.add_argument("--gate", type=float, help="CALDERA deployment gate on S")
    return p


def resolve_config(args) -> GBSEConfig:
    """Resolve config: defaults < data/gbse_config.json < CLI flags. ``input`` (dir or
    .zip) sets base; ``--output-dir`` (shared CLI flag) sets out; the timestamp is
    auto-detected from the directory unless ``--timestamp`` is given. Raises
    FileNotFoundError/ValueError on a missing or malformed config."""
    cfg = GBSEConfig()

    # config file: explicit --config, else gbse_config.json in the data/ dir
    default_cfg = Path(__file__).parent / "data" / "gbse_config.json"
    cfg_path = getattr(args, "config", None) or (
        str(default_cfg) if default_cfg.is_file() else None
    )
    if cfg_path:
        if not os.path.isfile(cfg_path):
            raise FileNotFoundError(f"--config file not found: {cfg_path}")
        cfg.merge(parse_any(cfg_path))
        logger.info(f"Config loaded from {cfg_path}")

    # CLI calibration / sigma overrides (only those supplied)
    cfg.merge({k: getattr(args, k, None) for k in ("sigma_yml", "tr", "dv", "dv_i", "gate")})
    if getattr(args, "output_dir", None):
        cfg.out = args.output_dir

    # input positional: directory or output.zip -> base
    inp = getattr(args, "input", None)
    if inp:
        if inp.lower().endswith(".zip"):
            import tempfile
            import zipfile

            tmp = tempfile.mkdtemp(prefix="gbse_ozx_")
            with zipfile.ZipFile(inp) as z:
                z.extractall(tmp)
            cand = os.path.join(tmp, "output")
            cfg.base = cand if os.path.isdir(cand) else tmp
        else:
            cfg.base = inp

    # timestamp: explicit flag wins; else auto-detect; else config/default
    if getattr(args, "timestamp", None):
        cfg.ts = args.timestamp
    else:
        detected = _detect_timestamp(cfg.base)
        if detected:
            cfg.ts = detected

    return cfg.validate()


def parse_any(path: str) -> dict:
    """Parse a pipeline artifact that may be prefixed with a text header banner
    and/or contain full-line `//` comments.

    Strategy: locate the JSON payload (first line beginning with `{`/`[`), drop
    full-line comments, then attempt strict JSON. Only if that fails fall back to
    scrubbing stray control characters (some artifacts embed raw newlines/tabs
    inside string values). Raises a clear, path-tagged error if both fail, rather
    than surfacing an opaque JSONDecodeError deep in the pipeline.
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    start = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith(("{", "["))), None)
    if start is None:
        raise ValueError(f"{path}: no JSON object/array found in file")
    body = "".join(ln for ln in lines[start:] if not ln.lstrip().startswith("//"))
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", body)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: invalid JSON ({e})") from e


def szss(A, B) -> float:
    if not A and not B:
        return 1.0
    d = max(len(set(A)), len(set(B)))
    return len(set(A) & set(B)) / d if d else 0.0


def lsc(logsource: str) -> str:
    return logsource.split("/")[-1] if "/" in logsource else logsource


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


PRIV_RANK = {
    "user": 0,
    "non-elevated": 0,
    "elevated": 1,
    "admin": 1,
    "admin_local": 2,
    "system": 3,
    "kernel": 4,
}


def build_conv_index(conv_notes: list):
    """Index conversion_notes by normalised converted_action (Linux) -> note."""
    idx, bits = [], None
    for n in conv_notes:
        idx.append((_norm(n["converted_action"]), n))
        if str(n["original_action"]).lower().startswith("bitsadmin"):
            bits = n["original_action"]
    return idx, bits


def derive_windows_command(linux_cmd: str, conv_idx, bitsadmin_orig, tech: str = ""):
    k = _norm(linux_cmd)

    for ck, n in conv_idx:
        if ck == k:
            return n["original_action"], "conversion_note"
    for ck, n in conv_idx:
        base = ck.split("...")[0].strip()
        if base and len(base) > 10 and (k.startswith(base) or base.startswith(k)):
            return n["original_action"], "conversion_note"

    m = re.match(r"^\s*wine\s+(.*)$", linux_cmd, re.I)
    if m:
        return m.group(1).strip(), "de_wine"

    m = re.match(r"^\s*ssh\s+\S+@([\d.]+)", linux_cmd, re.I)
    if m and tech == "T1021.001":
        return f"mstsc /v:{m.group(1)}", "technique_pattern"

    if tech == "T1562.001" and re.search(r"systemctl\s+stop\s+(ufw|firewalld)", linux_cmd, re.I):
        return "netsh advfirewall set allprofiles state off", "technique_pattern"

    if re.match(r"^\s*wget\s", linux_cmd, re.I) and ".exe" in linux_cmd.lower():
        url = re.search(r"(https?://\S+)", linux_cmd)
        dst = re.search(r"-O\s+(\S+)", linux_cmd)
        dst_win = dst.group(1).replace("/tmp/", "C:\\\\Windows\\\\Temp\\\\") if dst else "<dst>"
        win = (
            f'bitsadmin /transfer job /download /priority high '
            f'{url.group(1) if url else "<url>"} {dst_win}'
        )
        return win, "bitsadmin_map"

    win = re.sub(r"^\s*sudo\s+", "", linux_cmd).strip()
    return win, "cross_platform"


_KW = {
    "process": {
        "process",
        "execut",
        "exec ",
        "spawn",
        "command-line",
        "command line",
        "running",
        "execve",
        "auditd exec",
        "binary",
        "creation of",
        "creation event",
    },
    "network": {
        "network",
        "tcp",
        "udp",
        "http",
        "ssh",
        "scp",
        "ldap",
        "dns",
        "traffic",
        "listener",
        "outbound",
        "inbound",
        "smb",
        "webdav",
        "proxy",
        "ids",
        "upload",
        "download",
        "socket",
        "arp",
        "icmp",
        "web",
        "connection",
    },
    "file": {
        "file",
        "directory",
        "disk",
        "write",
        "read access",
        "core dump",
        "config",
        "zip",
        "log",
        "dump file",
        "file access",
        "file creation",
        "file system",
    },
    "identity": {
        "auth",
        "credential",
        "password",
        "account",
        "identity",
        "login",
        "privilege",
        "sudo",
        "session",
        "token",
        "secret",
        "dump",
    },
}


def parse_telemetry_expected(text: str) -> list:
    if not text or not isinstance(text, str):
        return []
    t = text.lower()
    return sorted(cls for cls, kws in _KW.items() if any(kw in t for kw in kws))


def _tags(tags: list) -> list:
    out = []
    for t in tags or []:
        m = re.match(r"attack\.(t\d{4}(?:\.\d{3})?)", str(t), re.I)
        if m:
            out.append(m.group(1).upper())
    return out


def load_sigma_rules(yml_path):
    yml_path = Path(yml_path)
    if not (_HAS_YAML and yml_path.exists()):
        raise RuntimeError(f"PyYAML and a Sigma rule library are required; not found: {yml_path}")
    with open(yml_path, encoding="utf-8") as f:
        raw = list(yaml.safe_load_all(f.read()))
    lin, win = [], []
    for doc in raw:
        if not doc:
            continue
        prod = doc.get("logsource", {}).get("product", "").lower()
        rule = {
            "rule_id": doc.get("id", ""),
            "name": doc.get("name", ""),
            "title": doc.get("title", ""),
            "logsource": f"{prod}/process_creation",
            "tags": _tags(doc.get("tags", [])),
            "tel": doc.get("x-gbse-telemetry", []),
        }
        (lin if prod == "linux" else win).append(rule)
    logger.info(
        f"Loaded sigma library: {len(lin)} Linux + {len(win)} Windows rules "
        f"from {yml_path.name}"
    )
    return lin, win


def inject_sigma(step: dict, lib: list) -> list:
    tech = step["technique_id"]
    tel = set(step.get("telemetry_classes", []))
    out = []
    for r in lib:
        tm = tech in r["tags"]
        ov = szss(tel, set(r["tel"]))
        if tm or ov >= 0.50:
            out.append(
                {
                    "rule_id": r["rule_id"],
                    "name": r.get("name", ""),
                    "title": r["title"],
                    "logsource": r["logsource"],
                    "logsource_category": lsc(r["logsource"]),
                    "attack_tag": tech,
                    "matched_tags": r["tags"],
                    "match_type": "both"
                    if (tm and ov >= 0.50)
                    else "technique"
                    if tm
                    else "telemetry",
                    "tele_overlap": round(ov, 4),
                }
            )
    return out


def build_windows_control(linux_seq: list, conv_notes: list, win_rules: list):
    conv_idx, bitsadmin_orig = build_conv_index(conv_notes)
    steps = []
    for s in linux_seq:
        e = copy.deepcopy(s)
        win_cmd, prov = derive_windows_command(
            e.get("command", ""), conv_idx, bitsadmin_orig, e.get("technique_id", "")
        )
        e["command"] = win_cmd
        e["win_command_provenance"] = prov
        e["os"] = "Windows"
        # Algorithm 1: structured observable classes from free-text intent
        e["telemetry_classes"] = parse_telemetry_expected(e.pop("telemetry_expected", ""))
        rp = e.pop("required_privilege", "user")
        e["execution_level"] = "elevated" if rp == "elevated" else "non-elevated"
        e["privilege_context"] = "elevated" if rp == "elevated" else "user"
        t = e.get("tactic", "")
        e["tactic"] = (
            [t.lower().replace(" ", "_").replace("-", "_")]
            if isinstance(t, str)
            else [x.lower().replace(" ", "_").replace("-", "_") for x in t]
        )
        tech = e.get("technique_id", "")
        e["parent_technique_id"] = tech.split(".")[0] if "." in tech else tech
        e.update(
            os_mappable=True,
            omission_reason=None,
            data_flow=None,
            privilege_delta="none",
            sigma_rules=[],
            d3fend_observables=[],
            execution_observables=[],
        )
        e.pop("dependencies_constraints", None)
        e.pop("original_step_id", None)
        steps.append(e)
    for i in range(1, len(steps)):
        p = PRIV_RANK.get(steps[i - 1]["privilege_context"], 0)
        c = PRIV_RANK.get(steps[i]["privilege_context"], 0)
        steps[i]["privilege_delta"] = "escalation" if c > p else "drop" if c < p else "none"
    for st in steps:
        st["sigma_rules"] = inject_sigma(st, win_rules)
    return steps


def build_linux_variant(var_seq: list, lin_rules: list):
    steps = []
    for s in var_seq:
        e = copy.deepcopy(s)
        if "telemetry" in e and "telemetry_classes" not in e:
            e["telemetry_classes"] = e.pop("telemetry")
        e["telemetry_classes"] = sorted(e.get("telemetry_classes", []))
        el = e.get("execution_level", "non-elevated")
        e["privilege_context"] = "elevated" if el == "elevated" else "user"
        e["os"] = "Linux"
        t = e.get("tactic", "")
        e["tactic"] = (
            [t.lower().replace(" ", "_").replace("-", "_")]
            if isinstance(t, str)
            else [x.lower().replace(" ", "_").replace("-", "_") for x in t]
        )
        tech = e.get("technique_id", "")
        e["parent_technique_id"] = tech.split(".")[0] if "." in tech else tech
        e.update(
            os_mappable=True,
            omission_reason=None,
            data_flow=None,
            privilege_delta="none",
            sigma_rules=[],
        )
        e.pop("original_step_id", None)
        steps.append(e)
    for i in range(1, len(steps)):
        p = PRIV_RANK.get(steps[i - 1]["privilege_context"], 0)
        c = PRIV_RANK.get(steps[i]["privilege_context"], 0)
        steps[i]["privilege_delta"] = "escalation" if c > p else "drop" if c < p else "none"
    for st in steps:
        st["sigma_rules"] = inject_sigma(st, lin_rules)
    return steps


def telemetry_classes_match(g_c, g_v, threshold=0.50, strict=True):
    """Per-step telemetry correspondence between control and variant.

    Mirrors the L2 node-matching relation (m2): each step-id-aligned
    (control, variant) pair must have Szymkiewicz-Simpson telemetry overlap
    above the telemetry threshold (strict '>' by default, matching theta_tele).
    Passes iff every aligned pair clears it. Returns (passed, detail).
    """
    by_c = {s["step_id"]: s for s in g_c}
    by_v = {s["step_id"]: s for s in g_v}
    mismatches = []
    for sid in sorted(by_c.keys() | by_v.keys()):
        C1 = set(by_c.get(sid, {}).get("telemetry_classes", []))
        C2 = set(by_v.get(sid, {}).get("telemetry_classes", []))
        ov = szss(C1, C2)
        ok = (ov > threshold) if strict else (ov >= threshold)
        if not ok:
            mismatches.append((sid, sorted(C1), sorted(C2), round(ov, 3)))
    if not mismatches:
        rel = ">" if strict else ">="
        return True, f"all {len(by_c.keys() | by_v.keys())} steps szss {rel} {threshold}"
    detail = f"{len(mismatches)}/{len(g_v)} below threshold: " + "; ".join(
        f"S{sid} {c}->{v} szss={ov}" for sid, c, v, ov in mismatches
    )
    return False, detail


def compute_auto(g_c, g_v, os_violations):
    ctrl_ids = {s["step_id"] for s in g_c}
    var_ids = {s["step_id"] for s in g_v}
    # Align control vs variant by step_id rather than list position, so a
    # reordered or one-sided step surfaces as a mismatch instead of silently
    # passing (and the comparisons stay correct if the lists ever differ in
    # length). For the recorded run (both sides step_id 1..29 in order) this is
    # identical to positional zip.
    by_c = {s["step_id"]: s for s in g_c}
    by_v = {s["step_id"]: s for s in g_v}
    ids = sorted(ctrl_ids | var_ids)

    def aligned(getter, default=None):
        return [
            (getter(by_c[i]) if i in by_c else default, getter(by_v[i]) if i in by_v else default)
            for i in ids
        ]

    tid = aligned(lambda s: s["technique_id"])
    par = aligned(lambda s: s["parent_technique_id"])
    VALID = {"file", "network", "process", "identity", "registry", "module", "driver"}
    all_v = {t for s in g_v for t in s["telemetry_classes"]}
    extra = all_v - VALID
    multi = sum(1 for s in g_v if len(s["telemetry_classes"]) >= 2)

    def npv(s):
        el = s.get("execution_level", s.get("privilege_context", "user"))
        return "elevated" if el in ("elevated", "admin") else "non-elevated"

    def rt(s):
        t = s.get("tactic", [])
        return t[0].lower() if t else ""

    priv = aligned(npv, default="non-elevated")
    tac = aligned(rt, default="")
    checks = {
        "missing_steps": (ctrl_ids <= var_ids, f"{len(ctrl_ids-var_ids)} missing"),
        "extra_steps": (var_ids <= ctrl_ids, f"{len(var_ids-ctrl_ids)} extra"),
        "os_constructs_valid": (
            len(os_violations) == 0,
            f"{len(os_violations)} Windows constructs (wine/.exe) " f"surviving in Linux G_v",
        ),
        "technique_ids_match": (
            all(c == v for c, v in tid),
            f"{sum(1 for c,v in tid if c!=v)} mismatches",
        ),
        "parent_technique_ids_match": (
            all(c == v for c, v in par),
            "all match" if all(c == v for c, v in par) else "mismatches",
        ),
        "telemetry_classes_match": telemetry_classes_match(g_c, g_v),
        "extra_telemetry_classes": (len(extra) == 0, f"extra={sorted(extra)}" if extra else "none"),
        "telemetry_diversity": (len(all_v) >= 3, f"{len(all_v)} distinct classes"),
        "telemetry_multi_class": ((multi / len(g_v)) >= 0.80, f"{multi}/{len(g_v)} multi-class"),
        "technique_sequence_match": (
            all(c == v for c, v in tid),
            f"identical {len(tid)}-step sequence"
            if all(c == v for c, v in tid)
            else f"{sum(1 for c,v in tid if c!=v)}/{len(tid)} steps differ",
        ),
        "tactic_sequence_match": (all(a == b for a, b in tac), "same per step"),
        "privilege_progression_match": (
            all(c == v for c, v in priv),
            f"{sum(1 for c,v in priv if c!=v)} mismatches",
        ),
    }
    p = sum(1 for ok, _ in checks.values() if ok)
    return checks, p, len(checks), round(p / len(checks), 4)


def bipartite_ged(c_steps, v_steps, match_fn):
    nc, nv = len(c_steps), len(v_steps)
    C = np.full((nc + nv, nc + nv), INF)
    for i, cs in enumerate(c_steps):
        for j, vs in enumerate(v_steps):
            C[i][j] = 0.0 if match_fn(cs, vs) else 1.0
    for i in range(nc):
        C[i][nv + i] = 1.0
    for j in range(nv):
        C[nc + j][j] = 1.0
    for i in range(nv):
        for j in range(nc):
            C[nc + i][nv + j] = 0.0
    row, col = linear_sum_assignment(C)
    ged = float(C[row, col].sum())
    norm = max(nc, nv)
    sim = round(max(0.0, 1.0 - ged / norm), 4)
    fails = []
    for i in range(nc):
        j = col[i]
        if j < nv and C[i][j] >= 1.0:
            fails.append(
                {
                    "ctrl_step": c_steps[i]["step_id"],
                    "ctrl_tech": c_steps[i]["technique_id"],
                    "var_step": v_steps[j]["step_id"],
                    "var_tech": v_steps[j]["technique_id"],
                    "ctrl_tel": c_steps[i]["telemetry_classes"],
                    "var_tel": v_steps[j]["telemetry_classes"],
                    "cause": _diagnose(c_steps[i], v_steps[j]),
                }
            )
    return ged, sim, fails, norm


def _diagnose(cs, vs) -> str:
    if cs["technique_id"] != vs["technique_id"]:
        return f"technique_mismatch: {cs['technique_id']} != {vs['technique_id']}"
    T1, T2 = set(cs.get("tactic", [])), set(vs.get("tactic", []))
    if T1 and T2 and szss(T1, T2) < 0.50:
        return f"tactic_drift: szss={szss(T1,T2):.3f}<0.50"
    C1, C2 = set(cs["telemetry_classes"]), set(vs["telemetry_classes"])
    ov = szss(C1, C2)
    if ov <= 0.50:
        return f"telemetry_drift: overlap={ov:.3f}<=0.50, ctrl={sorted(C1)}, var={sorted(C2)}"
    L1 = {lsc(r["logsource"]) for r in cs.get("sigma_rules", [])}
    L2 = {lsc(r["logsource"]) for r in vs.get("sigma_rules", [])}
    return f"sigma_gap: overlap={szss(L1,L2):.3f}<0.50"


def m0(c, v):
    return c["technique_id"] == v["technique_id"]


def m1(c, v):
    if not m0(c, v):
        return False
    T1, T2 = set(c.get("tactic", [])), set(v.get("tactic", []))
    return szss(T1, T2) >= 0.50 if (T1 and T2) else True


def m2(c, v):
    if not m1(c, v):
        return False
    C1, C2 = set(c["telemetry_classes"]), set(v["telemetry_classes"])
    return szss(C1, C2) > 0.50 if (C1 or C2) else True  # STRICT >


def m3_chained(c, v):
    if not m2(c, v):
        return False
    L1 = {lsc(r["logsource"]) for r in c.get("sigma_rules", [])}
    L2 = {lsc(r["logsource"]) for r in v.get("sigma_rules", [])}
    return szss(L1, L2) >= 0.50 if (L1 or L2) else True


def m3_independent(c, v):
    if not m0(c, v):
        return False
    L1 = {lsc(r["logsource"]) for r in c.get("sigma_rules", [])}
    L2 = {lsc(r["logsource"]) for r in v.get("sigma_rules", [])}
    return szss(L1, L2) >= 0.50 if (L1 or L2) else True


def gold_control_divergence(eval_result: dict, var_steps: list, base: str):
    """Technique-level divergence: the Windows gold control vs the Linux variant,
    aligned by step_id.

    Route A (preferred): load the structured gold control file referenced by
    eval_result.metadata.control_file and compare technique_id per step.
    Route B (fallback): if that file is absent, parse the gold technique from
    eval_result.technique_ids_match.detail, but take the VARIANT technique from
    structured data (var_steps), and raise if a non-empty detail parses to zero
    records (the silent-failure mode of the old regex-only implementation).
    """
    var_by_id = {s["step_id"]: s.get("technique_id") for s in var_steps}

    # --- Route A: structured gold control ---
    fname = eval_result.get("metadata", {}).get("control_file")
    if fname:
        path = os.path.join(base, os.path.basename(fname))
        if os.path.isfile(path):
            doc = parse_any(path)
            gold = (
                doc.get("procedure", {}).get("action_sequence")
                or doc.get("action_sequence")
                or doc.get("steps")
            )
            if isinstance(gold, list) and gold and "technique_id" in gold[0]:
                return [
                    {
                        "gold_step": g["step_id"],
                        "gold_win_technique": g["technique_id"],
                        "variant_lin_technique": var_by_id.get(g["step_id"]),
                    }
                    for g in gold
                    if g["technique_id"] != var_by_id.get(g["step_id"])
                ]

    # --- Route B: validated fallback (gold from prose, variant from data) ---
    detail = eval_result.get("technique_ids_match", {}).get("detail", "")
    pat = re.compile(
        r"Control (\d+) \((T\d{4}(?:\.\d{3})?)\) vs " r"Variant \d+ \((T\d{4}(?:\.\d{3})?)\)"
    )
    pairs = pat.findall(detail)
    if detail.strip() and not pairs:
        raise ValueError(
            "technique_ids_match.detail is non-empty but parsed 0 "
            "records; upstream format may have changed:\n"
            f"{detail[:160]}"
        )
    out = []
    for step_s, gtech, _vtech_prose in pairs:
        sid = int(step_s)
        vtech = var_by_id.get(sid)
        if vtech is None:
            logger.warning(f"gold S{sid} has no matching variant step_id")
        if gtech != vtech:
            out.append(
                {"gold_step": sid, "gold_win_technique": gtech, "variant_lin_technique": vtech}
            )
    return out


def run_gbse(args, logger=None) -> int:
    """Run GBSE for one pipeline output directory. Returns a process exit code.

    Signature matches the project's ``run_*(args, logger, ...)`` dispatch
    convention. ``args`` is the parsed CLI namespace (see ``add_gbse_subparser``).
    """
    log = logger or globals()["logger"]

    try:
        cfg = resolve_config(args)
    except (FileNotFoundError, ValueError) as e:
        log.error(str(e))
        return 1

    base, ts = cfg.base, cfg.ts
    os.makedirs(cfg.out, exist_ok=True)

    missing = [f"{f}_{ts}.json" for f in INPUT_FILES if not os.path.isfile(f"{base}/{f}_{ts}.json")]
    if missing:
        log.error(
            f"Missing input file(s) under '{base}' for ts={ts}: "
            f"{', '.join(missing)}. Point at the pipeline output directory "
            f"(or output.zip), or set --timestamp."
        )
        return 1

    try:
        inp = parse_any(f"{base}/input_procedure_{ts}.json")
        var = parse_any(f"{base}/full_output_{ts}.json")
        conv = parse_any(f"{base}/conversion_result_{ts}.json")["conversion_notes"]
        ev = parse_any(f"{base}/evaluation_result_{ts}.json")
        viol = parse_any(f"{base}/os_violations_{ts}.json")
    except (ValueError, KeyError) as e:
        log.error(f"Failed to load run artifacts: {e}")
        return 1

    lin_seq = inp["procedure"]["action_sequence"]
    var_seq = var["procedure"]["action_sequence"]
    log.info(
        f"Loaded spine: {len(lin_seq)} steps | conversion_notes: {len(conv)} | "
        f"os_violations: {len(viol)}"
    )

    try:
        lin_rules, win_rules = load_sigma_rules(cfg.sigma_yml)
    except RuntimeError as e:
        log.error(str(e))
        return 1

    g_c = build_windows_control(lin_seq, conv, win_rules)
    g_v = build_linux_variant(var_seq, lin_rules)

    prov: dict = {}
    for s in g_c:
        prov[s["win_command_provenance"]] = prov.get(s["win_command_provenance"], 0) + 1
    log.info(f"G_c Windows command provenance: {prov}")
    log.debug("Sample reconstructed Windows commands:")
    for s in g_c[:8]:
        log.debug(
            f"  S{s['step_id']:2d} {s['technique_id']:<12} "
            f"[{s['win_command_provenance']:<15}] {s['command'][:48]}"
        )

    checks, ap, at, auto = compute_auto(g_c, g_v, viol)
    log.info("Automated evaluation (G_c=Windows control vs G_v=Linux variant):")
    for k, (ok, d) in checks.items():
        log.info(f"  {'PASS' if ok else 'FAIL'} {k}: {d}")
    log.info(f"  AUTO = {ap}/{at} = {auto:.4f}")

    c_ns, v_ns = copy.deepcopy(g_c), copy.deepcopy(g_v)
    for s in c_ns:
        s["sigma_rules"] = []
    for s in v_ns:
        s["sigma_rules"] = []
    layers = [
        ("Baseline", m0, g_c, g_v),
        ("L1", m1, g_c, g_v),
        ("L2", m2, g_c, g_v),
        ("L3_pre_sigma", m3_chained, c_ns, v_ns),
        ("L3_post_sigma", m3_chained, g_c, g_v),
        ("L3_independent", m3_independent, g_c, g_v),
    ]
    log.info(f"GBSE layer results (Windows->Linux, normaliser={len(g_c)}):")
    lr: dict = {}
    for lbl, fn, cs, vs in layers:
        ged, sim, fails, norm = bipartite_ged(cs, vs, fn)
        band = "High" if sim > 0.80 else "Medium" if sim >= 0.60 else "Low"
        lr[lbl] = dict(ged=ged, sim=sim, fails=fails, norm=norm, band=band)
        log.info(f"  {lbl}: GED={ged:.1f}, Sim={sim:.4f} [structural band: {band}]")
        for f in fails:
            log.info(f"    x S{f['ctrl_step']}({f['ctrl_tech']}): {f['cause']}")

    tr, dv, dv_i, gate, weights = cfg.tr, cfg.dv, cfg.dv_i, cfg.gate, cfg.weights
    states = [
        ("Baseline", lr["Baseline"]["sim"], dv),
        ("L1_tactic", lr["L1"]["sim"], dv),
        ("L2_telemetry", lr["L2"]["sim"], dv),
        ("L3_pre_sigma", lr["L3_pre_sigma"]["sim"], dv),
        ("L3_post_sigma", lr["L3_post_sigma"]["sim"], dv),
        ("L3_independent", lr["L3_independent"]["sim"], dv_i),
    ]
    log.info("Composite scores:")
    score: dict = {}
    for st, sim_v, dv_v in states:
        bcf = round(weights["bcf_auto"] * auto + weights["bcf_sim"] * sim_v, 4)
        s = round(weights["s_bcf"] * bcf + weights["s_tr"] * tr + weights["s_dv"] * dv_v, 4)
        # Fidelity bands (0.80/0.60) are a fixed descriptive taxonomy; the
        # deployment gate (cfg.gate) is the separately-tunable cutoff on S.
        cls = "High Fidelity" if s > 0.80 else "Medium Fidelity" if s >= 0.60 else "Low Fidelity"
        score[st] = dict(sim=sim_v, bcf=bcf, tr=tr, dv=dv_v, s=s, cls=cls, caldera=s >= gate)
        log.info(f"  {st:<22}: Sim={sim_v:.4f} BCF={bcf:.4f} S={s:.4f} [{cls}]")
    best = max(score, key=lambda k: score[k]["s"])
    req_tr = round(
        (gate - weights["s_bcf"] * score[best]["bcf"] - weights["s_dv"] * score[best]["dv"])
        / weights["s_tr"],
        4,
    )
    approved = score[best]["s"] >= gate
    log.info(
        f"CALDERA gate (S>={gate:.2f}): Best S={score[best]['s']} ({best}) | "
        f"Required TR={req_tr} | Current TR={tr} | Approved: {approved}"
    )

    gold = gold_control_divergence(ev, g_v, base)
    log.info("Gold-control technique divergence (Windows gold vs Linux variant):")
    for g in gold:
        log.info(
            f"  gold S{g['gold_step']}: WIN {g['gold_win_technique']:<12} "
            f"-> LIN variant {g['variant_lin_technique']}"
        )
    log.info(f"  {len(gold)} technique substitutions in the gold-control window.")

    now = datetime.now(UTC).isoformat()
    ctrl_doc = {
        "gbse_schema_version": "2.0-winlin",
        "generated_at": now,
        "sigma_library": f"sigma_rules_gbse.yml — Windows W01-W{len(win_rules):02d} "
        f"({len(win_rules)} rules)",
        "source": "WINDOWS control G_c — per-step Windows commands reconstructed from "
        "the conversion record (conversion_notes original_action / de-wine / "
        "bitsadmin map)",
        "metadata": {
            "procedure_id": "alphv_blackcat_windows_ctrl_genuine",
            "procedure_os": "windows",
            "pipeline_stage": "reconstructed-windows-control",
            "sigma_injection_os": "windows",
            "reconstruction_note": "Windows commands grounded in "
            "conversion_result.conversion_notes (original_action), the provable "
            "de-wine inverse of wine-wrapped PEs, and the documented bitsadmin<-wget "
            "mapping. ATT&CK technique_id/tactic preserved (OS-independent).",
            "graph_topology": {"V": len(g_c), "E_sequential": len(g_c) - 1},
            "enrichment": "Algorithm 1: telemetry_expected -> telemetry_classes",
            "automated_evaluation": {"pass": ap, "total": at, "auto": auto},
        },
        "procedure": {"action_sequence": g_c},
    }
    var_doc = {
        "gbse_schema_version": "2.0-winlin",
        "generated_at": now,
        "sigma_library": f"sigma_rules_gbse.yml — Linux L01-L{len(lin_rules):02d} "
        f"({len(lin_rules)} rules)",
        "source": f"LINUX variant G_v — full_output_{ts}.json (LLM translation)",
        "metadata": {
            "procedure_id": "alphv_blackcat_linux_var_genuine",
            "procedure_os": "linux",
            "pipeline_stage": "post-enrichment",
            "sigma_injection_os": "linux",
            "run_timestamp": ts,
            "os_violation_count": len(viol),
            "graph_topology": {"V": len(g_v), "E_sequential": len(g_v) - 1},
        },
        "procedure": {"action_sequence": g_v},
    }
    ged_doc = {
        "generated_at": now,
        "design": "Windows->Linux. G_c=reconstructed Windows control, G_v=Linux variant. "
        "L0/L1 GED=0 measures technique/tactic preservation across the OS boundary "
        "(faithful translation preserves ATT&CK labels). Discriminating signal: L2 "
        "observable classes, L3 OS-specific Sigma logsource, and os_constructs "
        "(Windows constructs surviving into Linux).",
        "layer_results": {
            lbl: {
                "ged": v["ged"],
                "sim": v["sim"],
                "norm": v["norm"],
                "structural_band": v["band"],
                "failed_pairs": v["fails"],
            }
            for lbl, v in lr.items()
        },
        "composite_scores": score,
        "caldera_gate": {
            "threshold": gate,
            "best_S": score[best]["s"],
            "best_state": best,
            "required_TR": req_tr,
            "current_TR": tr,
            "approved": approved,
        },
        "automated_evaluation": {
            "checks": {k: {"passed": p, "detail": d} for k, (p, d) in checks.items()},
            "pass_count": ap,
            "total": at,
            "auto": auto,
        },
        "gold_control_divergence": {
            "control_file": ev.get("metadata", {}).get("control_file"),
            "technique_substitutions": gold,
            "note": (
                f"{len(gold)} gold-control step(s) diverge from the Linux variant at the "
                f"technique level (e.g. {gold[0]['gold_win_technique']} -> "
                f"{gold[0]['variant_lin_technique']}). The per-step reconstruction aligns each "
                f"step technique by construction and so does not surface this divergence."
                if gold
                else "No gold-control technique divergence: every gold step's technique matches the "
                "Linux variant under the per-step reconstruction."
            ),
        },
        "windows_command_provenance": prov,
        "run_config": asdict(cfg),
    }

    paths = {
        "ctrl": os.path.join(cfg.out, "winlin_control_enriched.json"),
        "var": os.path.join(cfg.out, "winlin_variant_enriched.json"),
        "ged": os.path.join(cfg.out, "winlin_ged_results.json"),
    }
    for doc, p in zip([ctrl_doc, var_doc, ged_doc], paths.values(), strict=True):
        with open(p, "w") as f:
            json.dump(doc, f, indent=2)
        log.info(f"Saved {p}")

    return 0


def main(argv=None) -> int:
    """Standalone entry point: ``python -m procedure_generator.gbse <input> [opts]``.

    Within the project, prefer wiring ``add_gbse_subparser``/``run_gbse`` into
    cli.py so GBSE shares the top-level ``--output-dir``/``--verbose`` flags.
    """
    parser = argparse.ArgumentParser(
        prog="procedure-generator gbse",
        description="Graph-based structural evaluation of a translated procedure run",
    )
    parser.add_argument(
        "--output-dir", dest="output_dir", default=OUT, help="Directory for GBSE result files"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "input", help="Pipeline output directory (or output.zip) with the run artifacts"
    )
    parser.add_argument(
        "--timestamp", help="Run timestamp; auto-detected from the input directory if omitted"
    )
    parser.add_argument("--config", help="Path to a gbse JSON config file (calibration overrides)")
    parser.add_argument("--sigma", dest="sigma_yml", help="Path to the Sigma rule library")
    parser.add_argument("--tr", type=float, help="Technical Realism (manual)")
    parser.add_argument("--dv", type=float, help="Defensive Value (manual)")
    parser.add_argument(
        "--dv-i", dest="dv_i", type=float, help="Defensive Value for independent-L3"
    )
    parser.add_argument("--gate", type=float, help="CALDERA deployment gate on S")
    args = parser.parse_args(argv)

    if args.verbose:
        os.environ["LOGLEVEL"] = "DEBUG"

    return run_gbse(args, ProcedureLogger(__name__))


if __name__ == "__main__":
    import sys

    sys.exit(main())
