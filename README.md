# fre-research

LLM-based adversary procedure transformation framework.

## Installation

Install dependencies:

```
uv sync
```

If uv is not installed, follow instructions [here](https://docs.astral.sh/uv/getting-started/installation/#installing-uv)

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=http://localhost:11434/v1  # For Ollama
OPENAI_MODEL=gpt-oss:20b                    # Default model
```

## Testing

Run the test suite with:

```bash
uv run pytest
```

This runs the unit tests under `tests/`, covering the GBSE scoring helpers, the
evaluation measures, Sigma rule loading (including a duplicate-key regression
guard), config validation, and the replication empty-output guard.

The tests require the `dev` dependency group, which `uv sync` installs by
default. A few tests that exercise the replication node are skipped
automatically when the workflow runtime dependencies are unavailable.

## Commands

### Replication Mode

Verbatim reproduction of a procedure:

```
uv run ./src/procedure_generator/cli.py replication ./blackcat_procedure.md
```

### Variant Mode

Convert procedure from one OS to another:

```
uv run ./src/procedure_generator/cli.py variant ./blackcat_procedure.md --source-os windows --target-os linux
```

### Enrichment Mode

Add D3FEND observables to a procedure:

```
uv run ./src/procedure_generator/cli.py enrich ./output/variant_output.json
```

### Full Pipeline Mode

Run variant + enrichment + evaluation (optional):

```bash
# Without evaluation
uv run ./src/procedure_generator/cli.py full ./blackcat_procedure.md \
    --source-os windows --target-os linux

# With evaluation against a control file
uv run ./src/procedure_generator/cli.py full ./blackcat_procedure.md \
    --source-os windows --target-os linux \
    --control ./control/gold_standard.json
```

#### Persisting intermediate artifacts (`--save-output`)

By default the `full` command writes only `full_output_<ts>.json` (plus the
evaluation CSV). The `--save-output` flag additionally writes every
intermediate pipeline artifact to its own `<name>_<ts>.json` / `.txt` file in
the output directory. **GBSE consumes these artifacts**, so a run intended for
graph-based evaluation must enable it:

```bash
uv run ./src/procedure_generator/cli.py --save-output full ./blackcat_procedure.md \
    --source-os windows --target-os linux \
    --control ./control/gold_standard.json
```

Two requirements to produce the full set GBSE needs:

- `--save-output` must be set, otherwise `input_procedure_<ts>.json` and
  `conversion_result_<ts>.json` are never written.
- `--control <file>` must be provided, otherwise `evaluation_result_<ts>.json`
  and `os_violations_<ts>.json` are never written (the evaluation phase is
  skipped without a control file).

> **Note:** `--save-output` is a top-level flag, so it must appear *before* the
> `full` subcommand (as shown above), not after it.

A successful run with both flags emits all five artifacts GBSE requires, sharing
one timestamp: `input_procedure_<ts>.json`, `full_output_<ts>.json`,
`conversion_result_<ts>.json`, `evaluation_result_<ts>.json`, and
`os_violations_<ts>.json`.

### Graph-Based Structural Evaluation (GBSE)

Score a completed translation run by comparing the reconstructed Windows control
graph against the Linux variant graph (see [GBSE](#graph-based-structural-evaluation-gbse-1) below):

```bash
# Point at the pipeline output directory; the timestamp is auto-detected
uv run ./src/procedure_generator/cli.py gbse ./output/

# Or pin a specific run and override calibration constants
uv run ./src/procedure_generator/cli.py gbse ./output/ \
    --timestamp 1774278112.367423 \
    --sigma ./src/procedure_generator/data/sigma_rules_gbse.yml \
    --tr 0.43 --dv 0.51 --dv-i 0.65 --gate 0.80
```

## Execution Modes

This framework provides five generation modes, each building on the previous,
plus a separate post-hoc analysis stage, Graph-Based Structural Evaluation
(GBSE), that scores a completed run:

### Replication Mode (`replication`)

**Purpose:** Verbatim reproduction of a procedure to test LLM fidelity.

**Workflow:**

```
replicate → END
```

| Node | Description |
|------|-------------|
| `replicate` | LLM reproduces the input procedure exactly as written |

**Output:** Plain text file with reproduced procedure.

---

### Replication + Structure Mode (`replication_and_structure`)

**Purpose:** Reproduce procedure and convert to structured JSON format with ATT&CK mappings.

**Workflow:**

```
replicate → translate → validate → END
```

| Node | Description |
|------|-------------|
| `replicate` | LLM reproduces the input procedure |
| `translate` | Convert to structured TTPOutputBase JSON with ATT&CK mappings |
| `validate` | Verify and correct the structured output |

**Output:** JSON file with `TTPOutputBase` structure.

---

### Variant Mode (`variant`)

**Purpose:** Convert procedure from one operating system to another while preserving attack semantics.

**Workflow:**

```
replicate → translate → validate → extract_environment → convert_environment → convert → refine → output → END
```

| Node | Description |
|------|-------------|
| `replicate` | LLM reproduces the input procedure |
| `translate` | Convert to structured TTPOutputBase JSON |
| `validate` | Verify and correct the structured output |
| `extract_environment` | Identify hosts and their OS in the procedure |
| `convert_environment` | Map hosts to target OS |
| `convert` | Transform commands for target OS |
| `refine` | Fix syntax issues and validate commands |
| `output` | Assemble final FinalOutput structure |

**Output:** JSON file with `FinalOutput` structure including metadata and validation summary.

---

### Enrichment Mode (`enrich`)

**Purpose:** Add D3FEND observables to an existing procedure JSON.

**Workflow:**

```
enrich → output → END
```

| Node | Description |
|------|-------------|
| `enrich` | LLM identifies D3FEND artifacts for each step |
| `output` | Assemble EnrichedFinalOutput with telemetry classes |

**Output:** JSON file with `EnrichedFinalOutput` structure including observables per step.

---

### Full Pipeline Mode (`full`)

**Purpose:** Complete transformation pipeline: variant conversion + D3FEND enrichment + optional evaluation.

**Workflow (without evaluation):**

```
replicate → translate → validate → extract_environment → convert_environment → convert → refine → variant_output → bridge_to_enrichment → enrich → enrichment_output → full_output → END
```

**Workflow (with evaluation via --control):**

```
replicate → translate → validate → extract_environment → convert_environment → convert → refine → variant_output → bridge_to_enrichment → enrich → enrichment_output → bridge_to_evaluation → structural_compare → os_construct_check → telemetry_compare → evaluation_output → full_output → END
```

| Node | Phase | Description |
|------|-------|-------------|
| `replicate` | Variant | LLM reproduces the input procedure |
| `translate` | Variant | Convert to structured JSON |
| `validate` | Variant | Verify structured output |
| `extract_environment` | Variant | Identify hosts and OS |
| `convert_environment` | Variant | Map hosts to target OS |
| `convert` | Variant | Transform commands |
| `refine` | Variant | Fix and validate commands |
| `variant_output` | Variant | Assemble variant output |
| `bridge_to_enrichment` | Bridge | Prepare state for enrichment |
| `enrich` | Enrichment | Add D3FEND observables |
| `enrichment_output` | Enrichment | Assemble enriched output |
| `bridge_to_evaluation` | Bridge | Prepare state for evaluation |
| `structural_compare` | Evaluation | Check step coverage and technique IDs |
| `os_construct_check` | Evaluation | Detect OS-specific violations |
| `telemetry_compare` | Evaluation | Compare telemetry classes |
| `evaluation_output` | Evaluation | Assemble evaluation result |
| `full_output` | Final | Combine all outputs |

**Output:**

- JSON file with `FullPipelineOutput` (variant + enrichment + evaluation)
- CSV file with evaluation results (if --control provided)

---

### Graph-Based Structural Evaluation (`gbse`)

**Purpose:** Score how faithfully a Windows→Linux translation preserves
*defender-relevant* structure, using graph-based analysis. GBSE treats each
procedure as a graph and calculates graph distance to measure translation fidelity.

**Inputs:** GBSE does not run the LLM pipeline. It consumes the artifacts of a
prior `full --save-output --control` run, all sharing one timestamp under the
input directory:

| File | Used for |
|------|----------|
| `input_procedure_<ts>.json` | Spine for the reconstructed Windows control graph (G_c) |
| `full_output_<ts>.json` | The Linux variant graph (G_v), used unmodified |
| `conversion_result_<ts>.json` | `conversion_notes` ground the per-step Windows command reconstruction |
| `evaluation_result_<ts>.json` | Gold-control technique divergence |
| `os_violations_<ts>.json` | Windows constructs (`wine`/`.exe`) surviving into Linux |

The timestamp is auto-detected from `input_procedure_<ts>.json` unless
`--timestamp` is given. A missing file aborts the run with a list of what's
absent — re-run `full` with both `--save-output` and `--control` if so.

**How it works:**

1. **Graph model.** Each procedure is a directed attributed graph `G = (V, E)`.
   Nodes carry `technique_id`, `tactic[]`, `privilege_context`,
   `telemetry_classes[]`, and `sigma_rules[]`; edges are typed (sequential,
   conditional-privilege, dataflow/telemetry-trigger).
2. **Windows control reconstruction.** The Windows control graph `G_c` is rebuilt
   step-for-step from the run's own conversion record so each control step
   carries the genuine Windows command the translation acted on. The grounding
   source is recorded per step in `win_command_provenance`
   (`conversion_note` > `de_wine` > `bitsadmin_map` > `cross_platform` >
   `technique_pattern`).
3. **Layered node matching.** Each layer adds exactly one constraint, so the
   layer at which similarity first drops localizes the deviation. Set overlaps
   use the Szymkiewicz–Simpson coefficient (szss):
   - **L0 (Technique)**: `technique_id` equality.
   - **L1 (Tactic)**: L0 plus tactic overlap (szss ≥ 0.50).
   - **L2 (Telemetry)**: L1 plus strict telemetry-class overlap (szss > 0.50). The critical layer for Windows→Linux drift.
   - **L3 (Sigma logsource)**: L2 plus Sigma logsource overlap (szss ≥ 0.50): detectability drift.
   - **L3-independent (L3-i)**: drops the L2 prerequisite; requires only L0 plus logsource overlap, so detection coverage stays visible even when L2 fails.
4. **Structural similarity.** Computed per layer as a normalized Graph Edit
   Distance via the Riesen–Bunke bipartite (Hungarian) approximation:
   `Sim_struct = 1 − GED / max(|V_c|, |V_v|)`.
5. **Composite scores.** Behaviour Chain Fidelity
   `BCF = 0.5·auto_pass + 0.5·Sim_struct`, and overall
   `S = 0.4·BCF + 0.3·TR + 0.3·DV`, where Technical Realism (TR) and Defensive
   Value (DV) are supplied via flags/config. A state is approved for CALDERA
   deployment when its `S` meets the gate (default 0.80). *(Weights are initial
   analytic settings pending empirical calibration.)*

**Calibration flags:** `--tr`, `--dv`, `--dv-i` (DV for independent-L3), and
`--gate` override the defaults; `--config` points to a JSON file with the same
keys (and a `weights` block); `--sigma` overrides the Sigma rule library path.
CLI flags take precedence over the config file, which takes precedence over the
built-in defaults.

**Output:** three files in the output directory:

- `winlin_control_enriched.json`: reconstructed Windows control graph G_c (per-step provenance, telemetry classes, injected Sigma rules).
- `winlin_variant_enriched.json`: enriched Linux variant graph G_v.
- `winlin_ged_results.json`: per-layer GED/similarity, composite scores, CALDERA gate verdict, automated-evaluation tally, gold-control divergence, and provenance distribution.

A summary of every layer, the composite scores, and the gate decision is also
written to the run log.

## Evaluation

When a control (gold standard) file is provided to the `full` command, the pipeline evaluates the generated variant against twelve pass/fail measures. Results are output to a CSV file.

### Evaluation Measures

| Question ID | Measure | Question | Pass Condition |
|-------------|---------|----------|----------------|
| 1.1 | `technique_sequence_match` | Does the variant preserve the same ordered sequence of techniques as the control? | All techniques match in order |
| Unknown | `tactic_sequence_match` | Does the variant preserve the same ordered sequence of tactics as the control? | All tactics match in order |
| 1.4 | `missing_steps` | Are any steps in the control missing from the variant? | No missing steps |
| 1.7 | `privilege_progression_match` | Does the variant preserve the same privilege context progression as the control? | Collapsed privilege sequences match |
| 1.5 | `extra_steps` | Are any new steps present in the variant that are not in the control? | No extra steps |
| 2.4 (*Excluding from automated evaluation pending further development*) | `os_constructs_valid` | Does the procedure avoid Windows-only constructs on non-Windows systems? | No violations found |
| 3.1.2 | `technique_ids_match` | Do the variant and control map to the same ATT&CK technique IDs (exact)? | All technique IDs match exactly |
| 3.1.1 | `parent_technique_ids_match` | Do the variant and control map to the same parent ATT&CK techniques? | All parent techniques match |
| 3.1.3 | `telemetry_classes_match` | Does the variant generate the same telemetry classes as the control? | All control classes present |
| 3.2.9 | `missing_telemetry_classes` | Are any telemetry classes from the control missing? | No missing control classes (Derived from `telemetry_classes_match` by analyzing `telemetry_classes_detail` for missing classes) |
| 3.2.10 | `extra_telemetry_classes` | Are additional telemetry classes present in the variant? | No extra classes |
| 3.2.7 | `telemetry_diversity` | Does the variant have the same level of telemetry diversity as the control? | Variant count >= control count |
| 3.2.1 | `telemetry_multi_class` | Does execution generate telemetry in more than one telemetry class? | Variant has >= 2 classes |

---

### Measure 1: `technique_sequence_match`

**Question:** Does the variant preserve the same ordered sequence of techniques as the control?

**Scoring Logic:**

1. Build an ordered sequence of `(step_id, technique_id)` pairs from control steps in their natural order
2. For each variant step, map it to its control step using `original_step_id` (falls back to `step_id` if null)
3. For each control step in order, check if the corresponding variant step(s) have the same `technique_id`
4. **PASS** if all techniques match at each position in the sequence
5. **FAIL** if any control step is missing from the variant, or if any technique differs

**Detail on failure:** Lists each mismatch in format `"Step {ctrl_id}: {ctrl_technique} vs {variant_technique}"` or `"Step {ctrl_id}: missing in variant"`

**Example:**

- Control sequence: `[(1, T1078), (2, T1105), (3, T1003)]`
- Variant sequence: `[(1, T1078), (2, T1105), (3, T1003)]` → **PASS**
- Variant sequence: `[(1, T1078), (2, T1059), (3, T1003)]` → **FAIL** - Step 2 technique mismatch
- Variant sequence: `[(1, T1078), (3, T1003)]` → **FAIL** - Step 2 missing

**Note:** This measure ensures the attack maintains its logical progression and technique order during OS conversion. Unlike `technique_ids_match` which checks individual step mappings, this measure validates the overall sequence integrity.

---

### Measure 2: `tactic_sequence_match`

**Question:** Does the variant preserve the same ordered sequence of tactics as the control?

**Scoring Logic:**

1. For each control step in order, record its `tactic` field (e.g., "Initial Access", "Execution", "Persistence")
2. For each variant step, map it to its control step using `original_step_id` (falls back to `step_id` if null)
3. For each control step in order, check if the corresponding variant step(s) have the same `tactic`
4. **PASS** if all tactics match at each position in the sequence
5. **FAIL** if any control step is missing from the variant, or if any tactic differs

**Detail on failure:** Lists each mismatch in format `"Step {ctrl_id}: {ctrl_tactic} vs {variant_tactic}"` or `"Step {ctrl_id}: missing in variant"`

**Example:**

- Control sequence: `[(1, Initial Access), (2, Execution), (3, Credential Access)]`
- Variant sequence: `[(1, Initial Access), (2, Execution), (3, Credential Access)]` → **PASS**
- Variant sequence: `[(1, Initial Access), (2, Persistence), (3, Credential Access)]` → **FAIL** - Step 2 tactic mismatch
- Variant sequence: `[(1, Initial Access), (3, Credential Access)]` → **FAIL** - Step 2 missing

**Note:** This measure mirrors `technique_sequence_match` but operates on the higher-level tactic field. It ensures the attack maintains its tactical progression (kill chain order) during OS conversion.

---

### Measure 4: `privilege_progression_match`

**Question:** Does the variant preserve the same privilege context progression as the control?

**Scoring Logic:**

1. Extract `execution_level` ("elevated" or "non-elevated") from each control step in order
2. Collapse consecutive steps with the same privilege level (e.g., `["elevated", "elevated", "non-elevated"]` → `["elevated", "non-elevated"]`)
3. Repeat for variant steps (ordered by `original_step_id` mapping to control)
4. **PASS** if the collapsed sequences are identical
5. **FAIL** if the sequences differ

**Detail on failure:** Shows both sequences (e.g., `"Control: ['non-elevated', 'elevated', 'non-elevated'], Variant: ['elevated', 'non-elevated']"`)

**Example:**

- Control steps with execution_level: `["non-elevated", "elevated", "elevated", "non-elevated"]`
- Control collapsed: `["non-elevated", "elevated", "non-elevated"]`
- Variant (correct): `["non-elevated", "elevated", "elevated", "non-elevated"]` → collapsed: `["non-elevated", "elevated", "non-elevated"]` → **PASS**
- Variant (incorrect): `["elevated", "elevated", "elevated", "non-elevated"]` → collapsed: `["elevated", "non-elevated"]` → **FAIL**

**Note:** The `execution_level` field is populated during D3FEND enrichment based on whether each command requires elevated privileges (admin/sudo/root) or can run as a standard user.

---

### Measure 5: `missing_steps`

**Question:** Are any steps in the control missing from the variant?

**Scoring Logic:**

1. Extract `step_id` from each control step to build the set of control step IDs
2. For each variant step, get its `original_step_id` (falls back to `step_id` if null)
3. Build a mapping: which control step IDs have at least one variant step pointing to them
4. **PASS** if every control step ID has at least one corresponding variant step
5. **FAIL** if any control step ID has no variant steps mapped to it

**Detail on failure:** Lists the missing control step IDs (e.g., `"Missing control step IDs: 3, 7, 12"`)

**Example:**

- Control has steps: `[1, 2, 3, 4, 5]`
- Variant has steps with `original_step_id`: `[1, 2, 4, 5]`
- Result: **FAIL** - Step 3 is missing

---

### Measure 6: `extra_steps`

**Question:** Are any new steps present in the variant that are not in the control?

**Scoring Logic:**

1. Extract `step_id` from each control step to build the set of valid control step IDs
2. For each variant step, get its `original_step_id`
3. If a variant step's `original_step_id` does not exist in the control step ID set, it's an "extra" step
4. **PASS** if no variant steps have unmapped `original_step_id` values
5. **FAIL** if any variant steps point to non-existent control steps

**Detail on failure:** Lists the extra variant step IDs (e.g., `"Extra variant step IDs: 15, 16"`)

**Example:**

- Control has steps: `[1, 2, 3]`
- Variant step has `original_step_id: 99`
- Result: **FAIL** - Step 99 doesn't exist in control

---

### Measure 7: `os_constructs_valid`

**Question:** Does the procedure avoid Windows-only constructs on non-Windows systems?

**Scoring Logic:**

1. Only runs when `target_os` is `linux` or `macos`
2. **Pattern-based detection** scans each variant command for Windows-specific patterns:
   - Executables: `cmd.exe`, `powershell.exe`, `.exe`, `.bat`, `.ps1`
   - Paths: Drive letters (`C:\`), UNC paths (`\\server\`)
   - Registry: `HKLM`, `HKCU`, `HKEY_`
   - Commands: `net user`, `net localgroup`, `wmic`, `schtasks`, `reg add/delete/query`
3. **LLM-based validation** asks the model to identify any Windows-specific constructs the patterns missed
4. **PASS** if no violations found by either method
5. **FAIL** if any violations detected

**Detail on failure:** Describes violations found (e.g., `"Step 5: powershell.exe (pattern); Step 8: Windows-specific path (llm)"`)

---

### Measure 8: `technique_ids_match`

**Question:** Do the variant and control map to the same ATT&CK technique IDs (exact match)?

**Scoring Logic:**

1. For each control step, find all variant steps that map to it (via `original_step_id`)
2. Compare the control step's `technique_id` with each mapped variant step's `technique_id` using exact string comparison
3. **PASS** if every variant step has the same `technique_id` as its corresponding control step
4. **FAIL** if any technique ID differs (including subtechnique differences like `T1078.001` vs `T1078.002`)

**Detail on failure:** Lists each mismatch in format `"Control {ctrl_id} ({ctrl_technique}) vs Variant {var_id} ({var_technique})"`

**Example output:**

```
Control 1 (T1078.001) vs Variant 1 (T1021.001); Control 5 (T1087.002) vs Variant 5 (T1069.002)
```

This means:

- Control step 1 has technique `T1078.001`, but variant step 1 (which maps to control step 1) has `T1021.001`
- Control step 5 has technique `T1087.002`, but variant step 5 has `T1069.002`

**Note:** This measure requires exact technique ID match. Use `parent_technique_ids_match` for parent-level comparison that ignores subtechnique differences.

---

### Measure 9: `parent_technique_ids_match`

**Question:** Do the variant and control map to the same parent ATT&CK techniques (ignoring subtechnique)?

**Scoring Logic:**

1. For each control step, find all variant steps that map to it (via `original_step_id`)
2. Extract parent technique from each technique ID by removing the subtechnique suffix (e.g., `T1078.001` → `T1078`)
3. Compare parent techniques between control and variant steps
4. **PASS** if every variant step has the same parent technique as its corresponding control step
5. **FAIL** if any parent technique differs

**Detail on failure:** Lists each mismatch in format `"Control {ctrl_id} ({ctrl_technique}) vs Variant {var_id} ({var_technique})"`

**Example:**

- `T1078.001` vs `T1078.002` → **PASS** (both are `T1078`)
- `T1078.001` vs `T1078` → **PASS** (both are `T1078`)
- `T1078.001` vs `T1021.001` → **FAIL** (`T1078` vs `T1021`)

**Use case:** This measure is useful when subtechnique selection may vary due to OS conversion but the overall attack technique should remain the same.

---

### Measure 10: `telemetry_classes_match`

**Question:** Does the variant generate the same telemetry classes as the control?

**Scoring Logic:**

1. Collect all `telemetry_classes` arrays from every control step
2. Flatten into a single set of unique control telemetry classes
3. Collect all `telemetry_classes` arrays from every variant step
4. Flatten into a single set of unique variant telemetry classes
5. Compute: `missing = control_classes - variant_classes`
6. **PASS** if `missing` is empty (variant has all control classes)
7. **FAIL** if any control classes are missing from variant

**Detail on failure:** Lists missing classes (e.g., `"Missing telemetry classes: registry, persistence"`)

**Valid telemetry classes:** `process`, `file`, `network`, `identity`, `registry`, `persistence`, `ipc`, `email`, `database`, `other`

---

### Measure 11: `extra_telemetry_classes`

**Question:** Are additional telemetry classes present in the variant?

**Scoring Logic:**

1. Collect procedure-wide unique telemetry classes for control and variant (same as measure 6)
2. Compute: `extra = variant_classes - control_classes`
3. **PASS** if `extra` is empty (variant introduces no new classes)
4. **FAIL** if variant has telemetry classes not in control

**Detail on failure:** Lists extra classes (e.g., `"Extra telemetry classes: ipc, email"`)

---

### Measure 12: `telemetry_diversity`

**Question:** Does the variant have the same level of telemetry diversity as the control?

**Scoring Logic:**

1. Count unique telemetry classes in control: `control_count = len(control_classes)`
2. Count unique telemetry classes in variant: `variant_count = len(variant_classes)`
3. **PASS** if `variant_count >= control_count`
4. **FAIL** if `variant_count < control_count`

**Detail on failure:** Shows counts (e.g., `"Variant has 3 classes, control has 5"`)

---

### Measure 13: `telemetry_multi_class`

**Question:** Does execution generate telemetry in more than one telemetry class?

**Scoring Logic:**

1. Count unique telemetry classes in variant: `variant_count = len(variant_classes)`
2. **PASS** if `variant_count >= 2`
3. **FAIL** if `variant_count < 2`

**Detail on failure:** Shows count (e.g., `"Variant has only 1 telemetry class(es)"`)

**Note:** This measure is independent of the control file. It checks whether the variant procedure generates diverse enough telemetry for meaningful detection coverage.

---

### Step Mapping Logic

The evaluation correctly handles **1:N step mappings** where one control step may be split into multiple variant steps during OS conversion:

- Each variant step has an `original_step_id` field indicating which control step it originated from
- If `original_step_id` is null, the evaluation falls back to using the variant's `step_id`
- Multiple variant steps can share the same `original_step_id` (valid for step splits)

**Example:** If control step 5 is split into variant steps 5a and 5b (both with `original_step_id=5`), this is correctly recognized as covering control step 5, not as "extra steps".

### CSV Output Format

The evaluation results are written to `output/evaluation_{timestamp}.csv`:

```csv
source_file,control_file,source_os,target_os,evaluated_at,model,missing_steps_pass,missing_steps_detail,extra_steps_pass,extra_steps_detail,os_constructs_pass,os_constructs_detail,technique_ids_pass,technique_ids_detail,parent_technique_ids_pass,parent_technique_ids_detail,telemetry_classes_pass,telemetry_classes_detail,extra_telemetry_pass,extra_telemetry_detail,telemetry_diversity_pass,telemetry_diversity_detail,telemetry_multi_class_pass,telemetry_multi_class_detail,technique_sequence_pass,technique_sequence_detail,tactic_sequence_pass,tactic_sequence_detail,privilege_progression_pass,privilege_progression_detail,all_pass
```

| Column | Description |
|--------|-------------|
| `source_file` | Path to the input procedure file |
| `control_file` | Path to the control/gold standard file |
| `source_os` | Source operating system |
| `target_os` | Target operating system |
| `evaluated_at` | ISO timestamp of evaluation |
| `model` | LLM model used |
| `missing_steps_pass` | `true` if no steps are missing |
| `missing_steps_detail` | List of missing step IDs (empty if passed) |
| `extra_steps_pass` | `true` if no extra steps |
| `extra_steps_detail` | List of extra step IDs (empty if passed) |
| `os_constructs_pass` | `true` if no OS construct violations |
| `os_constructs_detail` | Description of violations (empty if passed) |
| `technique_ids_pass` | `true` if all technique IDs match exactly |
| `technique_ids_detail` | Mismatches in format "Control N (T1234) vs Variant M (T5678)" |
| `parent_technique_ids_pass` | `true` if all parent techniques match (ignores subtechnique) |
| `parent_technique_ids_detail` | Mismatches where parent techniques differ |
| `telemetry_classes_pass` | `true` if all control telemetry classes are in variant |
| `telemetry_classes_detail` | Missing telemetry classes (empty if passed) |
| `extra_telemetry_pass` | `true` if no extra telemetry classes in variant |
| `extra_telemetry_detail` | Extra telemetry classes (empty if passed) |
| `telemetry_diversity_pass` | `true` if variant has >= control's unique class count |
| `telemetry_diversity_detail` | Count comparison (empty if passed) |
| `telemetry_multi_class_pass` | `true` if variant has >= 2 telemetry classes |
| `telemetry_multi_class_detail` | Count if variant has < 2 classes (empty if passed) |
| `technique_sequence_pass` | `true` if technique sequence matches control |
| `technique_sequence_detail` | Sequence mismatches (empty if passed) |
| `tactic_sequence_pass` | `true` if tactic sequence matches control |
| `tactic_sequence_detail` | Tactic mismatches (empty if passed) |
| `privilege_progression_pass` | `true` if privilege progression matches control |
| `privilege_progression_detail` | Collapsed sequences if mismatch (empty if passed) |
| `all_pass` | `true` if all twelve measures passed |
