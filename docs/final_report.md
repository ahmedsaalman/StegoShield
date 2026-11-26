# StegoShield: Encrypted Steganography with a Detector-in-the-Loop Pre-flight Check

**Final Report**

Ahmed Salman 23L-0678 (7J) · Alishba Jamal Uddin Ahmed 23L-1002 (7J) · Kashmala 23L-0878 (7J)
National University of Computer and Emerging Sciences, Lahore

---

## Abstract

StegoShield hides AES-256-GCM encrypted messages in the least significant bits (LSBs) of PNG images, at pixel positions that only the key holder can compute. Before hiding, it tells the sender how detectable the message would be. A trained steganalysis detector scores a simulated embedding of the planned size. The same detector is available to defenders for scanning suspicious images. On 417 held-out covers from 180 unseen photographs, no message the pre-flight check rated *Low* risk was detected (0 of 540), while 88 % of those rated *High* were. The detector (ROC-AUC 0.868 overall, 4.1 % false alarms) finds LSB replacement reliably (AUC 0.886 at 5 % payload, 0.995 at 50 %). LSB matching is harder (0.651 at 5 %, 0.963 at 50 %), so the application hides with matching by default. Embedding is visually lossless (PSNR ≥ 54 dB at 50 % payload). Every tampering, wrong-key and lossy-transport attempt fails safely, with no partial output.

## 1. Problem

Encryption hides *what* is said, not *that* something secret is being said. In a monitored setting, visible ciphertext is itself a signal. Steganography hides the message in an innocent-looking cover image instead, but typical tools have three gaps:

1. **No guidance on the cover image or message size.** Users can't tell how much they can hide before a detector notices.
2. **Weak secrecy of the hidden data itself.** Many tools write recognisable headers or use positions anyone can recompute, which proves a message exists even when it can't be read.
3. **Hiding and detecting are separate.** Tools rarely use a detector to judge how safe an embedding is.

StegoShield closes all three: it measures risk before embedding, hides data that is indistinguishable from noise without the key, and detects hidden data with a trained model.

## 2. Objectives and scope

| Objective | Delivered |
|---|---|
| Authenticated encryption with a password or a public key | AES-256-GCM; PBKDF2-HMAC-SHA256 (600,000 iterations) or X25519 ECDH + HKDF |
| Keyed LSB embedding with no plaintext markers | Two-stage format v2 (§3.2); LSB replacement or matching |
| Steganalysis detector | Calibrated Random Forest on 258 statistical features (per-channel and inter-channel), threshold tuned for ≤ 5 % false alarms |
| Detector-in-the-loop pre-flight check | Capacity, Low/Medium/High risk, recommended safe size |
| Application with an Evaluation Lab | React + TypeScript web app on a stateless FastAPI back end, plus a CLI |
| Reproducible evaluation | Five experiment scripts, held-out covers only, fixed seeds |

**Out of scope, as proposed:** CNN detectors, a separate risk-regression model, adaptive or JPEG-domain steganography, audio and video carriers, real social-media tests, production hosting and user accounts. (One demo instance runs on Hugging Face Spaces so the examiners can try the app; it stores nothing.)

**Changes from the proposal.**
- The single-file Streamlit dashboard was replaced by a React front end and a FastAPI back end. This gave a production-grade UI (accessibility, light and dark themes, phone-width layouts) and a testable API. It is stateless: nothing uploaded is stored.
- A *Sample Pairs Analysis* feature was added to the detector (§3.4). Without it, the detector missed the 0.90 ROC-AUC sanity target.
- The detector was then improved beyond the proposal (§3.4): an inter-channel feature family, a dataset nine times larger (900 source photos instead of 100), and a decision threshold tuned to cap false alarms at 5 %. Overall ROC-AUC rose from 0.731 to 0.868, and LSB matching went from undetectable to detectable at larger payloads.
- The pre-flight check also accepts the planned message size as "safe" when its own simulated risk is Low (§3.3).

## 3. Design

### 3.1 Architecture

```
frontend/ (React)  ──HTTP──▶  api/ (FastAPI, stateless)  ──▶  ml/ (detector, pre-flight)  ──▶  core/ (crypto, embedding)
                                     └──▶ experiments/ (Evaluation Lab demos reuse the evaluation code)
```

`core/` has no ML or web dependencies. `api/` holds no crypto or embedding logic; it validates input, calls the lower layers and maps errors to one JSON error shape. API hardening: a Content Security Policy and other security headers, `Cache-Control: no-store`, a per-IP rate limit, upload and pixel limits, a bounded CPU worker pool, request IDs, and logs that never contain secrets.

### 3.2 Modules A and C: encryption and embedding (message format v2)

| Stage | Contents | Placed at |
|---|---|---|
| 1 | Password mode: 16-byte random salt. Public-key mode: 32-byte one-time X25519 public key, top bit randomised | Slots chosen by a cheap *locator* key (from the password or the recipient's public key) |
| 2 | 12-byte nonce, 4-byte masked length, ciphertext + 16-byte tag | Slots chosen by a key derived from the **secret** (PBKDF2 output or ECDH shared secret, via HKDF) |

Overhead is 48 bytes (password) or 64 bytes (public key). The magic bytes, version and mode are never embedded. They are bound into AES-GCM as additional authenticated data, so a changed header fails authentication.

Two design decisions answer weaknesses of the first version:
- **No cheap password oracle.** The locator only reaches the salt, which is fresh random bytes. Checking a password guess requires a full PBKDF2 run (≈230 ms) instead of a header check (≈3 ms).
- **A public-key holder can't find the message.** The recipient's public key only locates stage 1, a random one-time key. The message positions need the private key.

Each derived key has its own HKDF label. Wrong key, tampering and "no message" all raise the same error, so the error can't confirm that a message exists. Embedding uses **LSB replacement** or **LSB matching** (±1, the default). A sequential layout exists only as an experimental baseline.

### 3.3 Module B: pre-flight check

A copy of the cover receives seeded random bytes of the planned size, embedded exactly as the real pipeline would (pseudorandom slots, chosen algorithm). The detector then scores that copy. Encrypted data is indistinguishable from random bytes, so this is the score an analyst would see on the real stego image. The check also scores 5, 10, 25 and 50 % payload shares, and returns:

- the exact capacity, including format overhead;
- the risk probability and level (Low < 0.35 ≤ Medium ≤ 0.65 < High);
- the largest size that stays Low: the largest Low share, or the planned size if that is Low. If neither is Low, the cover is *not recommended*.

It runs in about 2 s for a 512×512 image. Without a trained detector it raises an error; there is no heuristic fallback.

### 3.4 Module D: detector

- **Data:** 2,100 PNG covers (512×512) from 900 DIV2K photos: five crops from each of the 100 validation photos and two from each of the 800 training photos. Each cover is embedded 16 ways: 4 payload ratios × sequential or pseudorandom layout × replacement or matching. That gives 35,700 rows.
- **Features (258):** 28 per colour channel (LSB-plane statistics, chi-square pairs-of-values attack, first-order difference residuals, co-occurrence statistics, texture/edge complexity, and Sample Pairs Analysis, SPA), plus 174 image-level inter-channel features: for the channel-difference planes R−G, G−B and B−R, the shares of neighbouring steps of size 0, 1 and 2, their 5×5 co-occurrences, and the correlation of first differences between channel pairs.
- **Training:** split by *source photo* (720 photos train, 180 test), so no photo's crops appear on both sides. Classes are balanced with sample weights. A 300-tree Random Forest is wrapped in `CalibratedClassifierCV`. Three choices are made on grouped validation folds inside the training split: the share of features sampled per split (20 % won), the calibration method (isotonic won), and the decision threshold. The test split is never used for any choice.
- **Threshold:** the lowest value (never below 0.5) that flags at most 5 % of clean training photos in out-of-fold predictions: **0.72**. Probabilities stay calibrated, so the pre-flight risk levels are unaffected; only the yes/no decision moves.

The first model reached only ROC-AUC 0.75 on the sanity slice (50 % sequential replacement; target ≥ 0.90). Whole-image statistics varied about 25× more between photos than embedding changed them. SPA estimates the embedding rate *relative to each image's own pixel pairs*, which removes that between-photo variation. It became the most important feature and lifted the slice to 0.998.

That model still could not see LSB matching (AUC 0.51–0.57), because matching leaves no pairs-of-values signature. Camera noise in demosaiced photos is strongly correlated across R, G and B, while ±1 embedding changes each channel independently. The inter-channel features capture exactly that, and with 800 more source photos they lifted matching at 50 % to AUC 0.963. At the default 0.5 threshold the improved model flagged 15 % of clean photos; the tuned 0.72 threshold cuts that to 4.1 % at unchanged AUC.

## 4. Evaluation

Every experiment uses only the 417 held-out covers (the 180 test photos). Each script re-checks its covers against a saved split file before running. Full tables, figures and reproduction commands are in [results.md](results.md).

### 4.1 Visual quality

| Payload | 5 % | 10 % | 25 % | 50 % |
|---|---|---|---|---|
| PSNR (dB) | 64.15 ± 0.02 | 61.14 ± 0.01 | 57.16 ± 0.01 | 54.15 ± 0.01 |
| SSIM, replacement | 0.99982 | 0.99964 | 0.99910 | 0.99820 |

Replacement and matching have the same PSNR (both change the same number of values by exactly 1). Even at 50 %, PSNR is far above the ~40 dB where differences become visible.

### 4.2 Detector performance (held-out covers)

| ROC-AUC (caught at threshold 0.72) | Replacement, pseudorandom | Replacement, sequential | Matching, pseudorandom | Matching, sequential |
|---|---|---|---|---|
| 5 % | 0.886 (50 %) | 0.824 (38 %) | 0.651 (9 %) | 0.609 (6 %) |
| 10 % | 0.953 (80 %) | 0.919 (65 %) | 0.778 (22 %) | 0.695 (11 %) |
| 25 % | 0.984 (94 %) | 0.972 (86 %) | 0.902 (50 %) | 0.832 (32 %) |
| 50 % | 0.995 (97 %) | 0.992 (96 %) | 0.963 (80 %) | 0.931 (64 %) |

Overall ROC-AUC is 0.868 and balanced accuracy 0.755; 4.1 % of clean photos are wrongly flagged, and 99.5 % of flagged images really carry a message. Replacement is detected reliably from small payloads up. Matching is clearly harder at every size, which is why it is the default, but large matching payloads are now caught most of the time.

| Detector version | Photos | Features | Overall AUC | Matching AUC at 50 % | Stego caught | False alarms |
|---|---|---|---|---|---|---|
| First (per-channel only, threshold 0.5) | 100 | 84 | 0.731 | 0.566 | 40 % | 1 % |
| Final (inter-channel, threshold 0.72) | 900 | 258 | **0.868** | **0.963** | **55 %** | **4.1 %** |

The first version was evaluated on only 20 held-out photos, so its figures are noisier.

### 4.3 Pre-flight validity

| Predicted level | Actually detected (all covers) | Smooth covers | Textured covers |
|---|---|---|---|
| Low | **0.0 %** (n = 540) | 0.0 % (n = 216) | 0.0 % (n = 324) |
| Medium | 1.7 % (n = 544) | 0.9 % (n = 228) | 2.2 % (n = 316) |
| High | **88.1 %** (n = 2,252) | 90.3 % (n = 1,220) | 85.4 % (n = 1,032) |

There were 3,336 trials: real format-v2 messages at the four standard sizes, both algorithms, judged at the 0.72 threshold. Predicted and actual probabilities agree closely (Spearman ρ = 0.985). The High band starts at 65 %, below the threshold, so High is a warning rather than a guarantee. The prediction is equally valid for smooth and textured covers. Contrary to the proposal's assumption, texture barely changes risk for this detector, because its strongest features measure embedding relative to each image.

### 4.4 Transport robustness

| Transport | Recovered | Failed safely | Unsafe |
|---|---|---|---|
| PNG re-save | 40 / 40 | 0 | 0 |
| JPEG quality 90 | 0 | 40 / 40 | 0 |
| JPEG quality 75 | 0 | 40 / 40 | 0 |
| Resize to 50 % | 0 | 40 / 40 | 0 |

The message survives lossless transport only. Every lossy trial failed safely, with no partial plaintext, no garbage output and no crash.

### 4.5 Security and integrity

All 32 security tests pass: bit flips in the packet or pixels, header tampering, wrong password, wrong private key, cropping, extraction with only the public key, password-guess cost, and a signature scan. The full automated suite has 174 Python tests (security, crypto, embedding, ML, experiments, API) and 27 front-end unit tests.

## 5. Limitations

- **LSB embedding is detectable.** Replacement is caught from small payloads (AUC 0.886 at 5 %). Matching is harder but not safe at large payloads: 80 % of 50 % payloads are caught. Stronger detectors (e.g. CNN-based steganalysis) would likely do better still, so small payloads remain the safe choice, which is what the pre-flight check recommends.
- **False alarms.** About 4 % of clean photos are flagged. A flag is strong evidence (99.5 % precision) but not proof.
- **No robustness to lossy transport.** JPEG recompression or resizing destroys the message; it fails safely but can't be recovered. Images must travel as files, not as photos that a messaging app recompresses.
- **Detector scope.** The detector was trained on one image source (DIV2K, 512×512 PNG crops from 900 photos). The inter-channel features rely on camera-like, cross-channel-correlated noise. Behaviour on other cameras, sizes or processing is unmeasured. Synthetic images (e.g. pure noise) are out of distribution.
- **Key encoding.** A valid X25519 public key is not a perfectly uniform bit string. Hiding that would need Elligator2 encoding. With one image this leaks at most about one bit of evidence.
- **Experiment variance.** The pre-flight and robustness experiments use the real pipeline, whose keys come from the operating system's random generator by design. Their individual scores vary slightly between runs; the quality and detector results are byte-identical.

## 6. Future work

- Adaptive, content-aware embedding (e.g. HUGO or WOW style costs) to lower detectability further.
- A CNN steganalyser, both as a stronger detector and to test whether matching remains hard to detect.
- JPEG-domain embedding, for messages that must survive recompression.
- Elligator2 encoding of the one-time public key.
- A more varied detector training set (several cameras, sizes and post-processing pipelines; DIV2K is already used in full).

## 7. Conclusion

StegoShield delivers the full pipeline the proposal set out: authenticated encryption, keyed embedding with nothing recognisable in the pixels, a calibrated detector, and a pre-flight check that uses the detector to advise the sender. The evaluation shows the pre-flight check is a dependable guide: a Low prediction was never detected in 125 trials. The main practical finding is that the embedding *algorithm* and the *payload size* matter far more than the cover's texture. LSB matching at small payloads stays hard to detect, while LSB replacement, or matching at large payloads, is caught reliably. Improving the detector with inter-channel features and a larger dataset raised overall ROC-AUC from 0.731 to 0.868 while holding false alarms near 4 %.

## Appendix: reproducing the results

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python -m ml.prepare_covers && python -m ml.dataset   # covers + feature table (~4 GB download, ~65 min)
python -m ml.train_detector                            # optional, ~20 min: the trained model is committed
python -m experiments.quality && python -m experiments.detector_eval
python -m experiments.preflight_eval && python -m experiments.robustness && python -m experiments.security
pytest                                                 # automated tests
```

All scripts default to seed 2026. Results are written to `experiments/results/` and `docs/figures/`.
