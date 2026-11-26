# StegoShield: Development Phases

Scope is defined in [revised_proposal.md](revised_proposal.md). Already working: encryption, embedding/extraction, CLI, feature extraction, dashboard skeleton (4 tabs), 40 passing tests.

Work runs in order. Each phase ends with passing tests and a commit to `main`.

| # | Phase | Time | Done when |
|---|---|---|---|
| 0 | Setup | ½ day | Python 3.12 venv, pinned deps, no warnings, `pytest` green, `streamlit run app.py` opens |
| 1 | Secure format v2 | 1 day | Attack tests pass: public key alone finds nothing, wrong password can't be confirmed cheaply |
| 2 | Dataset | ½–1 day | ~500 covers in `data/covers/`, feature CSV generated |
| 3 | Detector | 1 day | `models/detector.joblib` + metrics JSON, test-set ROC-AUC reported |
| 4 | Pre-flight check | ½ day | Risk score + recommended safe payload come from the detector |
| 5 | Experiments | 1 day | `docs/results.md` with tables + figures for all 5 evaluations |
| 6 | App + Evaluation Lab | 1 day | 5 tabs working end to end on the trained model |
| 7 | Report & demo | 1 day | Report done, demo rehearsed, `main` frozen |

---

## Phase 0: Setup
- Install Python 3.12, recreate `.venv`, pin versions in `requirements.txt`.
- Fix Pillow `mode=` deprecation warnings, remove the duplicated README content.
- Check that the app launches.

## Phase 1: Secure format v2
- **Two-stage layout:**
  - Stage 1 stores the salt (password mode) or one-time public key (asymmetric mode) at positions derived from the password or recipient key. These bytes are random, so finding them reveals nothing.
  - Stage 2 stores nonce, length and ciphertext at positions derived from the **secret** (the PBKDF2 output, or the ECDH shared secret).
- No `STSH`/version/mode in the embedded bits. They stay as authenticated header data checked by AES-GCM. The length field is masked with a key-derived value.
- Pick only the slots needed instead of shuffling every slot in the image.
- New tests: public-key-only extraction, cheap password confirmation, keyless extraction looks random.
- Update `docs/payload_format.md` and `tests/security_results.md`.

## Phase 2: Dataset
- Script to download DIV2K and cut 512×512 PNG crops → `data/covers/` (not committed).
- Features computed per channel (R, G, B) instead of on grayscale.
- Generate the CSV: covers × {5, 10, 25, 50%} × {sequential, pseudorandom} × {replacement, matching}.

## Phase 3: Detector
- `ml/train_detector.py`: split by cover → Random Forest → probability calibration → `models/detector.joblib`.
- Save metrics (accuracy, precision, recall, ROC-AUC) overall and per ratio, mode and algorithm, plus feature importances.

## Phase 4: Pre-flight check
- Rewrite `ml/risk.py`: hide random data of the planned size in a copy of the cover → detector probability = risk.
- Recommended safe payload = largest of 5/10/25/50% that stays Low (< 35%).
- Show exact capacity including the encryption overhead.

## Phase 5: Experiments (`experiments/`)
- `quality.py`: PSNR/SSIM per payload ratio.
- `detector_eval.py`: ROC curves; sequential vs pseudorandom, replacement vs matching.
- `preflight_eval.py`: predicted risk vs actual detection, smooth vs textured covers.
- `robustness.py`: extraction success after PNG re-save, JPEG q90/q75, 50% resize.
- Security results come from the test suite.
- Collect everything into `docs/results.md` + `docs/figures/`.

## Phase 6: App + Evaluation Lab
- Connect the trained detector and new risk check to tabs 2 and 4. Tab 3 uses format v2.
- **New tab 5, Evaluation Lab:** live quality, robustness, attack and detector-comparison demos, reusing the `experiments/` code.
- Warn when the cover is a JPEG, handle large images, fix Streamlit deprecations.

## Phase 7: Report & demo
- Final report from `revised_proposal.md` + `results.md`.
- Demo script: key generation → pre-flight check → hide → extract → detect → Evaluation Lab.

---

**If time runs short, cut in this order:** LSB matching experiments → resize robustness test → detector comparison in Evaluation Lab.
