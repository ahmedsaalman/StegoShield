# StegoShield: Project Phases

This is the authoritative definition of the development phases. Scope comes from [revised_proposal.md](revised_proposal.md); the short schedule view is [week_plan.md](week_plan.md). When the two disagree, this file wins.

**How to read a phase.** Each phase has the same six parts:

| Part | Meaning |
|---|---|
| **Goal** | The one outcome the phase exists to produce. |
| **Depends on** | Phases that must be closed first. |
| **Tasks** | The work, as a checklist. |
| **Deliverables** | Files that must exist (or change) when the phase closes. |
| **Exit criteria** | Checks that must all pass. A phase is not done until every box is ticked. |
| **Not in this phase** | Work that belongs elsewhere, to stop scope creep. |

**Status legend:** ✅ Done · 🟡 In progress · ⬜ Not started

---

## Overview

| # | Phase | Module(s) | Depends on | Estimate | Status |
|---|---|---|---|---|---|
| 0 | Setup & hygiene | all | none | ½ day | ✅ |
| 1 | Secure format v2 | A, C | 0 | 1 day | ✅ |
| 2 | Dataset | D | 0 | ½–1 day | ⬜ |
| 3 | Detector | D | 2 | 1 day | ⬜ |
| 4 | Pre-flight check | B | 1, 3 | ½ day | ⬜ |
| 5 | Experiments | all | 1, 3, 4 | 1 day | ⬜ |
| 6 | App + Evaluation Lab | UI | 4, 5 | 1 day | ⬜ |
| 7 | Report & demo | none | 6 | 1 day | ⬜ |

Total: about 6½–7 working days.

```mermaid
graph LR
  P0[0 Setup] --> P1[1 Format v2]
  P0 --> P2[2 Dataset]
  P2 --> P3[3 Detector]
  P1 --> P4[4 Pre-flight]
  P3 --> P4
  P1 --> P5[5 Experiments]
  P3 --> P5
  P4 --> P5
  P4 --> P6[6 App + Eval Lab]
  P5 --> P6
  P6 --> P7[7 Report & demo]
```

Phases 1 and 2 are independent and can run in parallel if two people are available.

---

## Rules that apply to every phase

**Phase gate (Definition of Done):**
- [ ] All exit criteria for the phase are ticked.
- [ ] `pytest` is green with no new warnings, and runs in under 10 s (slow tests marked `@pytest.mark.slow`).
- [ ] New behaviour has tests, including failure paths.
- [ ] Docs touched by the change are updated in the same commit (`payload_format.md`, `security_results.md`, `README.md`).
- [ ] The phase's status in the overview table above is updated.
- [ ] One commit (or a short series) on `main` with a message of the form `phase N: <what changed>`.

**Standing rules:**
- Never refactor and add features in the same commit.
- Datasets, cover images, and stego images are never committed. Only code, small fixtures, the final `models/detector.joblib`, metrics JSON, and figures are.
- Every script that uses randomness takes a seed and records it in its output.

**If time runs short, cut in this order:** LSB-matching experiments → resize robustness test → detector comparison in the Evaluation Lab. Nothing in Phases 1, 3, or 4 is cuttable.

---

## Phase 0: Setup & hygiene ✅

**Goal:** A clean, reproducible environment that anyone on the team can set up and run in five minutes.

**Depends on:** none

**Tasks:**
- [x] Python 3.12 `.venv`
- [x] Test suite green (56 passing, 8 s)
- [x] Remove duplicated README content
- [x] Fix Pillow `mode=` deprecation warnings
- [x] Pin exact versions in `requirements.txt` (`pip freeze`-checked, `==` not `>=`)
- [x] Split dev-only tools (`pytest`, `ruff`) into `requirements-dev.txt`
- [x] Add `ruff` for linting and formatting; one config in `pyproject.toml`
- [x] Register the `slow` pytest marker in `pyproject.toml`
- [x] Confirm `streamlit run app.py` opens with no errors in the terminal

**Deliverables:** `requirements.txt` (pinned), `requirements-dev.txt`, `pyproject.toml`

**Exit criteria:**
- [x] A fresh clone → `python3.12 -m venv .venv && pip install -r requirements-dev.txt && pytest` passes
- [x] `ruff check .` reports zero errors
- [x] `streamlit run app.py` loads all tabs with no exceptions

**Not in this phase:** Streamlit API deprecations inside `app.py` (Phase 6).

---

## Phase 1: Secure format v2 ✅

**Goal:** Embedded bits carry no plaintext markers and give nothing away to anyone without the secret. A wrong key fails safely, and an attacker cannot test password guesses cheaply.

**Depends on:** 0

**Tasks:**
- [x] **Two-stage layout:**
  - Stage 1 holds only random bytes: the salt (password mode) or the one-time public key (asymmetric mode), at positions derived from the password or the recipient's public key.
  - Stage 2 holds nonce, masked length, and ciphertext + tag, at positions derived from the **secret** (PBKDF2 output, or ECDH shared secret, via HKDF).
- [x] Remove `STSH`, version, and mode from the embedded bits. They remain as AAD that AES-GCM authenticates, but are not stored in pixels.
- [x] Mask the length field with a key-derived value.
- [x] Randomise the top bit of the stored X25519 public key (it is always 0 otherwise, so it would leak). Check that the receiver ignores this bit, which RFC 7748 requires.
- [x] Select only the slots needed, instead of permuting every slot in the image.
- [x] Keep the sequential mode as a clearly labelled *baseline only* option.
- [x] Bump the format version constant. v1 payloads do not need to stay readable.

**Deliverables:** updated `core/crypto.py`, `core/embed.py`, `core/pipeline.py`, `docs/payload_format.md` (v2), `tests/security_results.md`

**Exit criteria (each is an automated test):**
- [x] Round-trip works in both modes, with both LSB replacement and LSB matching.
- [x] Extracting with **only the recipient's public key** recovers nothing beyond random bytes.
- [x] Checking a wrong password costs a full PBKDF2 run (no cheap early reject from a stored marker or checksum).
- [x] Bits pulled from a stego image without the key pass a randomness check (e.g. monobit and chi-square at α = 0.01) just as random bytes do.
- [x] A wrong key, a flipped bit, header tampering, or a crop raises `AuthenticationError` or `InvalidPayloadError`. Garbage output never comes back.
- [x] No byte sequence `STSH` appears in the extracted LSB stream.

**Not in this phase:** UI changes (Phase 6), JPEG robustness (Phase 5 only *measures* it).

*Note:* `app.py` Hide & Extract was minimally rewired to the v2 pipeline functions, because the v1 functions it called no longer exist. No other UI changes.

---

## Phase 2: Dataset ⬜

**Goal:** A labelled, reproducible feature table built from real photographs, ready for training without leakage.

**Depends on:** 0

**Tasks:**
- [ ] `ml/prepare_covers.py`: download DIV2K and cut about 500 512×512 PNG crops into `data/covers/` (one crop per source image, fixed seed).
- [ ] Add `data/covers/` and `data/features/` to `.gitignore`.
- [ ] Change `ml/features.py` to compute every feature per channel (R, G, B) instead of on grayscale. Keep `FEATURE_NAMES` as the single source of feature order.
- [ ] Generate stego variants: covers × {5, 10, 25, 50 %} × {sequential, pseudorandom} × {replacement, matching}, using format v2 if Phase 1 is done (or random payload bytes otherwise).
- [ ] Write `data/features/features.csv` with columns `cover_id, label, ratio, layout, algorithm, <features…>`.

**Deliverables:** `ml/prepare_covers.py`, updated `ml/features.py` and `ml/dataset.py`, generation command in `README.md`

**Exit criteria:**
- [ ] The CSV has 500 cover rows + 500 × 16 stego rows (8,500 total), with no NaN or inf.
- [ ] Every row has a `cover_id`, so the split in Phase 3 can be done by cover.
- [ ] Running the script twice with the same seed gives byte-identical CSVs.
- [ ] Unit test: feature vector length == `len(FEATURE_NAMES)` for RGB input.

**Not in this phase:** model training, synthetic covers (kept only for unit tests).

---

## Phase 3: Detector ⬜

**Goal:** A calibrated Random Forest that outputs P(stego) for an image, with honest held-out metrics.

**Depends on:** 2

**Tasks:**
- [ ] `ml/train_detector.py`: split by `cover_id` (`GroupShuffleSplit`, 80/20, fixed seed), so no cover appears in both train and test.
- [ ] Balance classes (class weights, or sample one stego variant per cover per epoch; document which).
- [ ] Random Forest → `CalibratedClassifierCV` (isotonic or sigmoid, chosen on validation folds).
- [ ] Save the artifact as a dict: `{model, feature_names, format_version, trained_at, seed}`. The loader rejects artifacts whose `feature_names` differ from the current `FEATURE_NAMES`.
- [ ] Save `models/detector_metrics.json`: accuracy, precision, recall, ROC-AUC overall and per {ratio, layout, algorithm}, plus top-15 feature importances.
- [ ] Remove the risk regressor path from `ml/risk.py` (out of scope).

**Deliverables:** `ml/train_detector.py`, `models/detector.joblib`, `models/detector_metrics.json`, updated `ml/detector.py`

**Exit criteria:**
- [ ] Test: train and test `cover_id` sets are disjoint.
- [ ] Test-set ROC-AUC is reported for every slice in the metrics JSON.
- [ ] Sanity check: ROC-AUC ≥ 0.90 for 50 % sequential replacement. If it is lower, features or labels are broken, so investigate before moving on.
- [ ] Loading a model with mismatched feature names raises a clear error.
- [ ] `StegoDetector.predict(image)` returns probability + top contributing features in < 1 s for 512×512.

**Not in this phase:** CNNs, hyper-parameter sweeps beyond a small grid.

---

## Phase 4: Pre-flight check ⬜

**Goal:** Before embedding, the user gets an exact capacity, a detector-backed risk level, and a recommended safe payload size.

**Depends on:** 1 (exact overhead), 3 (detector)

**Tasks:**
- [ ] Rewrite `ml/risk.py`: embed seeded random bytes of the planned size into a copy of the cover → detector probability = risk.
- [ ] Risk levels as an `Enum`: **Low** < 0.35 ≤ **Medium** ≤ 0.65 < **High**. Thresholds are named constants.
- [ ] Recommended safe payload = largest of {5, 10, 25, 50 %} whose simulated risk is Low. If none is Low, the result says "this cover is not recommended".
- [ ] Capacity in bytes includes the format v2 overhead for the selected mode.
- [ ] Return a single result object (dataclass): capacity, planned ratio, risk probability, risk level, recommended max bytes, per-ratio risks.
- [ ] If no trained detector is present, raise a clear error the UI can show. No silent heuristic fallback.

**Deliverables:** `ml/risk.py`, `tests/test_risk.py`

**Exit criteria:**
- [ ] Same cover + same seed → identical risk result.
- [ ] Planned payload > capacity → `CapacityExceededError` with the numbers in the message.
- [ ] Smooth synthetic cover scores higher risk than a textured cover at the same ratio (sanity test).
- [ ] The full pre-flight check on a 512×512 image finishes in < 5 s.

**Not in this phase:** UI wiring (Phase 6), the validity experiment (Phase 5).

---

## Phase 5: Experiments ⬜

**Goal:** Reproducible numbers and figures for every row of the proposal's evaluation plan.

**Depends on:** 1, 3, 4

**Tasks** (all under `experiments/`, each script importable by the app and runnable from the command line):
- [ ] `quality.py`: PSNR and SSIM per payload ratio (5/10/25/50 %), mean ± std over the test covers.
- [ ] `detector_eval.py`: ROC curves; sequential vs pseudorandom; replacement vs matching; per ratio.
- [ ] `preflight_eval.py`: predicted risk level vs actual detection rate on held-out covers, split into smooth vs textured by median texture complexity.
- [ ] `robustness.py`: extraction success after PNG re-save, JPEG q90, JPEG q75, 50 % resize. Expected result: PNG succeeds and the rest **fail safely**, which is reported as such.
- [ ] Security results: pulled from the test suite into `tests/security_results.md`.
- [ ] `docs/results.md`: one table + one figure per experiment, with one or two sentences of interpretation each.

**Deliverables:** `experiments/*.py`, `experiments/results/*.csv`, `docs/figures/*.png`, `docs/results.md`

**Exit criteria:**
- [ ] Each script runs end to end from a clean checkout plus the dataset, with a fixed seed.
- [ ] All five evaluations in the proposal have a table in `results.md`.
- [ ] Figures have axis labels, units, and legends, and stay readable in greyscale print.
- [ ] No test-set cover was used in training (re-checked from the split file).

**Not in this phase:** real social-media upload tests (out of scope).

---

## Phase 6: App + Evaluation Lab ⬜

**Goal:** A five-tab Streamlit dashboard that runs the whole pipeline on the trained model and demos the evaluation live.

**Depends on:** 4, 5

**Tasks:**
- [ ] Tab 2 (Pre-Flight Check) uses the Phase 4 result object.
- [ ] Tab 3 (Hide & Extract) uses format v2.
- [ ] Tab 4 (AI Detector) uses the trained detector and shows top features.
- [ ] **New tab 5, Evaluation Lab:** live quality, robustness, attack, and detector-comparison demos that **import** the `experiments/` code. No duplication.
- [ ] Every tab handles its empty, loading, success, error, and "detector not trained" states.
- [ ] Warn when the uploaded cover is a JPEG; downscale or refuse images above a size limit, and say so.
- [ ] Fix Streamlit deprecations (e.g. `use_container_width` → `width`).
- [ ] `app.py` contains no crypto or ML logic, only calls into `core/` and `ml/`.

**Deliverables:** `app.py` (or `app.py` + `ui/` modules if it passes about 600 lines)

**Exit criteria:**
- [ ] Manual walkthrough passes: keys → pre-flight → hide → download → extract → detect → Evaluation Lab.
- [ ] Wrong password and tampered image show a clear message, not a stack trace.
- [ ] No Streamlit deprecation warnings in the terminal.
- [ ] Risk level is never conveyed by colour alone (label + icon + percentage).

**Not in this phase:** user accounts, public deployment (out of scope).

---

## Phase 7: Report & demo ⬜

**Goal:** A short final report and a rehearsed live demo; `main` frozen.

**Depends on:** 6

**Tasks:**
- [ ] Final report built from `revised_proposal.md` + `results.md` (problem, design, results, limitations, future work).
- [ ] Demo script: key generation → pre-flight check → hide → extract → detect → Evaluation Lab, with a fallback recording in case of laptop/network issues.
- [ ] Rehearse at least twice, timed.
- [ ] Tag the release: `git tag v1.0`.

**Deliverables:** `docs/final_report.pdf` (or `.md`), `docs/demo_script.md`, tag `v1.0`

**Exit criteria:**
- [ ] Report numbers match `results.md` exactly.
- [ ] Demo runs start to finish in the allotted time on the presentation machine.
- [ ] No commits to `main` after the tag except report typo fixes.

---

## Traceability

| Proposal item | Delivered in phase |
|---|---|
| Module A: Encryption & keys | 1 |
| Module B: Pre-flight check | 4 |
| Module C: Keyed embedding | 1 |
| Module D: Detector | 2, 3 |
| Eval: Visual quality | 5 (`quality.py`) |
| Eval: Detector performance | 3, 5 (`detector_eval.py`) |
| Eval: Pre-flight validity | 5 (`preflight_eval.py`) |
| Eval: Transport robustness | 5 (`robustness.py`) |
| Eval: Security & integrity | 1 (tests), 5 (`security_results.md`) |
| Deliverable 1: App + CLI | 6 |
| Deliverable 2: `models/detector.joblib` | 3 |
| Deliverable 3: Experiment scripts + results | 5 |
| Deliverable 4: Test suite | 0–6 |
| Deliverable 5: Report + demo | 7 |
