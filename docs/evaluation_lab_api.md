# Evaluation Lab: API contract for the front end

The back end for the Phase 6 Evaluation Lab page is done (`api/routes/lab.py`, `api/lab.py`, `api/schemas.py`; tests in `tests/test_api_lab.py`). This file is what the React page needs. Live docs: `/api/docs`, tag "evaluation lab".

## Endpoints

| Method | Path | Body | Typical time (512×512) | Needs detector |
|---|---|---|---|---|
| GET | `/api/lab/results` | none | instant | no |
| POST | `/api/lab/quality` | `multipart/form-data`, field `image` | ~1.5 s | no |
| POST | `/api/lab/robustness` | same | ~0.2 s | no |
| POST | `/api/lab/attacks` | same | ~0.5 s | no |
| POST | `/api/lab/detector-comparison` | same | ~4–5 s | **yes** (503 otherwise) |

Uploads go through the same `load_cover_image` as `/api/detect` (PNG, JPEG, BMP, WebP; general size limits), plus a Lab-only cap of **1,048,576 pixels** (e.g. 1024×1024), because each demo processes the image many times.

## Types (add to `frontend/src/lib/api.ts`, mirroring `api/schemas.py`)

```ts
export type LabOutcome = "recovered" | "failed_safely" | "unsafe";

export interface QualityPoint { algorithm: EmbeddingAlgorithm; payload_percent: number; psnr_db: number | null; ssim: number }
export interface LabQuality { points: QualityPoint[] }                       // 8 points: 4 shares × 2 algorithms

export interface TransportTrial { transport: "png_resave" | "jpeg_q90" | "jpeg_q75" | "resize_50"; label: string; outcome: LabOutcome }
export interface LabRobustness { message_bytes: number; trials: TransportTrial[] }   // label is display text, e.g. "JPEG q90"

export interface AttackTrial { attack: string; description: string; outcome: LabOutcome }
export interface LabAttacks { trials: AttackTrial[] }                         // first trial is "control" (expected: recovered)

export interface DetectorPoint { algorithm: EmbeddingAlgorithm; payload_percent: number; probability: number; is_detected: boolean }
export interface LabDetectorComparison { clean_probability: number; threshold: number; points: DetectorPoint[] }

export interface SliceAuc { algorithm: EmbeddingAlgorithm; layout: "pseudorandom" | "sequential"; payload_percent: number; roc_auc: number }
export interface PreflightValidityRow { texture: "all" | "smooth" | "textured"; predicted_level: RiskLevel; n_trials: number; actual_detection_rate: number }
export interface RobustnessRow { transport: string; label: string; n_trials: number; recovered_rate: number; failed_safely_rate: number; unsafe_rate: number }
export interface QualityRow { algorithm: EmbeddingAlgorithm; payload_percent: number; psnr_mean_db: number; ssim_mean: number }
export interface LabResults {
  seed: number; held_out_covers: number;                                      // 100
  detector: SliceAuc[]; preflight_validity: PreflightValidityRow[]; robustness: RobustnessRow[]; quality: QualityRow[];
}
```

Rates and probabilities are 0–1: format probabilities with `formatProbability`, and rates with `formatPercent(rate * 100)` (`formatPercent` takes 0–100, like `payload_percent`).

## Errors

| Code | Status | When | Front-end note |
|---|---|---|---|
| `image_too_large` | 413 | over the general limit **or** the 1 MP Lab cap | existing title; the message says what to do |
| `detector_unavailable` | 503 | detector comparison without a model | existing title; show as the "not ready" state for that demo only |
| `lab_results_unavailable` | 503 | `/api/lab/results` when the result CSVs are missing | **new code**: add a title in `ErrorAlert.tsx`, e.g. "Saved results not available" |
| `invalid_image`, `unsupported_format`, `validation_error` | 4xx | as for `/api/detect` | existing |

## What each demo should convey (copy hints)

- **Saved results** (no upload needed, show first): held-out numbers from `docs/results.md`. Pre-flight: predicted Low → 0 % actually detected, High → 88 %. Detector: AUC 0.87 overall with 4 % false alarms; replacement AUC 0.89–1.00, matching 0.65 (5 %) to 0.96 (50 %). Robustness: PNG recovers; JPEG/resize fail safely.
- **Quality:** PSNR stays above ~54 dB even at 50 %, invisible to the eye. Both algorithms look identical.
- **Robustness:** "Recovered" only for PNG re-save. JPEG/resize show **"Failed safely"**, the intended behaviour (nothing leaks), not an error.
- **Attacks:** control = "Recovered"; every attack = "Failed safely". `unsafe` should never appear; if it does, show it as a danger state.
- **Detector comparison:** clean score vs replacement (flagged from ~10 %) vs matching (passes at small payloads, flagged from ~25 %). This is the case for LSB matching being the default and for keeping messages small.

Outcomes and detection must not rely on colour alone (skill §6.5): use `StatusBadge` with icon + words.
