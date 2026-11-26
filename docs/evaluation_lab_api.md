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
| GET | `/api/lab/samples` | none | instant | no |
| GET | `/api/lab/samples/{id}/image` | none | instant | no |
| POST | `/api/lab/samples/{id}/run` | JSON `{"payload_percent": 1–50}` | ~1.5–2 s per sample | **yes** (503 otherwise) |
| GET | `/api/lab/messages` | none | instant | no |
| POST | `/api/lab/messages/{id}/run` | `multipart/form-data`, field `image` | ~1–2 s per message (512 px image) | **yes** (503 otherwise) |

### Live sample run

The 8 built-in samples are 512×512 crops of DIV2K photos from the detector's **held-out** split (`api/samples/`, listed in `manifest.json` with their source cover id; `tests/test_lab_samples.py` checks they are held out). They are ordered smooth → textured (3 smooth, 3 medium, 2 textured by the held-out set's own thirds). DIV2K is licensed for academic research.

For one sample and one payload share, `run` returns, for **each algorithm**: the pre-flight prediction for that size (`PreflightChecker.predict_risk`), the detector's score on a **real** format-v2 stego image (public-key mode, fresh keys, seeded message bytes), PSNR/SSIM, the number and share of changed colour values, a 256 px JPEG preview of the stego image and a PNG map of the **centre 128×128 pixels at full resolution** (one dot = one changed value, coloured by channel). Fresh keys mean detector scores vary by a few points between runs; photos near the 72 % threshold can flip. The page runs the samples two at a time and updates as each one finishes (~10 s for all 8).

### Your image × sample messages

Six built-in texts (`api/sample_texts.py`, fictional and original): a one-line note (75 B), a chat excerpt (385 B), an email (1,001 B), a three-page letter (3,751 B), a field report (12,620 B) and a long dossier (40,196 B). `GET /api/lab/messages` returns them with the full text so the page can show exactly what gets hidden.

`POST /api/lab/messages/{id}/run` hides that text in the **uploaded** image (public-key mode, fresh keys) with each algorithm. If it doesn't fit, the response has `fits: false`, the capacity, and no results. Otherwise, for each algorithm it returns:

- the pre-flight prediction and the detector's real score, PSNR/SSIM, and changed values and pixels;
- five **safety checks** on the stego image: reveal with the right key (expected: recovered), with another private key, after flipping half of the lowest bits, after a JPEG q90 re-save, and after a 50 % resize (all expected: failed safely);
- an **exposure map**. The image is split into 16 px blocks scored by texture (mean absolute Laplacian of luminance), and the flattest third is marked. It reports the share of changes that landed there, and boxes the 64 px **hotspot** around the flat block with the most changes. `overview_image` is a ≤448 px JPEG: the image dimmed to grey, flat blocks tinted red, changed pixels cyan, hotspot boxed in yellow. `hotspot_original` and `hotspot_stego` are full-resolution PNG crops, before and after, with changed pixels in cyan;
- the detector's top three `top_signals` (feature and z-score against clean photos). The page names only those at least 1σ out.

The detector scores the whole image, so the map shows *where the evidence sits*, not a per-region verdict. Embedding scatters bits uniformly, so about a third of the changes land in the flattest third; adaptive embedding that avoids flat areas is future work.

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
| `unknown_sample` | 404 | a sample id not in the manifest | the page only uses ids from `/api/lab/samples` |
| `unknown_text` | 404 | a text id not in `api/sample_texts.py` | the page only uses ids from `/api/lab/messages` |
| `invalid_image`, `unsupported_format`, `validation_error` | 4xx | as for `/api/detect` | existing |

## What each demo should convey (copy hints)

- **Saved results** (no upload needed, show first): held-out numbers from `docs/results.md`. Pre-flight: predicted Low → 0 % actually detected, High → 88 %. Detector: AUC 0.87 overall with 4 % false alarms; replacement AUC 0.89–1.00, matching 0.65 (5 %) to 0.96 (50 %). Robustness: PNG recovers; JPEG/resize fail safely.
- **Quality:** PSNR stays above ~54 dB even at 50 %, invisible to the eye. Both algorithms look identical.
- **Robustness:** "Recovered" only for PNG re-save. JPEG/resize show **"Failed safely"**, the intended behaviour (nothing leaks), not an error.
- **Attacks:** control = "Recovered"; every attack = "Failed safely". `unsafe` should never appear; if it does, show it as a danger state.
- **Detector comparison:** clean score vs replacement (flagged from ~10 %) vs matching (passes at small payloads, flagged from ~25 %). This is the case for LSB matching being the default and for keeping messages small.

Outcomes and detection must not rely on colour alone (skill §6.5): use `StatusBadge` with icon + words.
