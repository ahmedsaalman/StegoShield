# StegoShield: Encrypted Steganography with a Detector-in-the-Loop Pre-flight Check

**Final Report**

Ahmed Salman 23L-0678 (7J) · Alishba Jamal Uddin Ahmed 23L-1002 (7J) · Kashmala 23L-0878 (7J)
National University of Computer and Emerging Sciences, Lahore

---

## Abstract

StegoShield hides AES-256-GCM encrypted messages in the least significant bits (LSBs) of PNG images, at pixel positions that only the key holder can compute. Before hiding, it tells the sender how detectable the message would be. A trained steganalysis detector scores a simulated embedding of the planned size. The same detector is available to defenders for scanning suspicious images. On 100 held-out photographs, no message the pre-flight check rated *Low* risk was detected (0 of 125), while 99.3 % of those rated *High* were. The detector finds LSB replacement reliably (ROC-AUC 0.866 at 5 % payload, 0.998 at 50 %) but not LSB matching (≤ 0.566). That's why the application hides with matching by default. Embedding is visually lossless (PSNR ≥ 54 dB at 50 % payload). Every tampering, wrong-key and lossy-transport attempt fails safely, with no partial output.

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
| Steganalysis detector | Calibrated Random Forest on 84 per-channel statistical features |
| Detector-in-the-loop pre-flight check | Capacity, Low/Medium/High risk, recommended safe size |
| Application with an Evaluation Lab | React + TypeScript web app on a stateless FastAPI back end, plus a CLI |
| Reproducible evaluation | Five experiment scripts, held-out covers only, fixed seeds |

**Out of scope, as proposed:** CNN detectors, a separate risk-regression model, adaptive or JPEG-domain steganography, audio and video carriers, real social-media tests, public deployment and user accounts.

**Changes from the proposal.**
- The single-file Streamlit dashboard was replaced by a React front end and a FastAPI back end. This gave a production-grade UI (accessibility, light and dark themes, phone-width layouts) and a testable API. It is stateless: nothing uploaded is stored.
- A *Sample Pairs Analysis* feature was added to the detector (§3.4). Without it, the detector missed the 0.90 ROC-AUC sanity target.
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

- **Data:** 500 PNG covers (512×512, five crops from each of 100 DIV2K validation photos). Each cover is embedded 16 ways: 4 payload ratios × sequential or pseudorandom layout × replacement or matching. That gives 8,500 rows.
- **Features (84):** 28 per colour channel: LSB-plane statistics, chi-square pairs-of-values attack, first-order difference residuals, co-occurrence statistics, texture/edge complexity, and Sample Pairs Analysis (SPA).
- **Training:** split by *source photo* (80 photos train, 20 test), so no photo's crops appear on both sides. Classes are balanced with sample weights. A 300-tree Random Forest is wrapped in `CalibratedClassifierCV`; the calibration method is chosen on grouped validation folds (isotonic won). The test split is never used for any choice.

The first model reached only ROC-AUC 0.75 on the sanity slice (50 % sequential replacement; target ≥ 0.90). Whole-image statistics varied about 25× more between photos than embedding changed them. SPA estimates the embedding rate *relative to each image's own pixel pairs*, which removes that between-photo variation. It became the most important feature and lifted the slice to 0.998.

## 4. Evaluation

Every experiment uses only the 100 held-out covers (the 20 test photos). Each script re-checks its covers against a saved split file before running. Full tables, figures and reproduction commands are in [results.md](results.md).

### 4.1 Visual quality

| Payload | 5 % | 10 % | 25 % | 50 % |
|---|---|---|---|---|
| PSNR (dB) | 64.15 ± 0.02 | 61.14 ± 0.02 | 57.16 ± 0.01 | 54.15 ± 0.01 |
| SSIM, replacement | 0.99982 | 0.99964 | 0.99911 | 0.99824 |

Replacement and matching have the same PSNR (both change the same number of values by exactly 1). Even at 50 %, PSNR is far above the ~40 dB where differences become visible.

### 4.2 Detector performance (ROC-AUC on held-out covers)

| Payload | Replacement, pseudorandom | Replacement, sequential | Matching, pseudorandom | Matching, sequential |
|---|---|---|---|---|
| 5 % | 0.866 | 0.803 | 0.512 | 0.507 |
| 10 % | 0.922 | 0.905 | 0.520 | 0.516 |
| 25 % | 0.986 | 0.973 | 0.537 | 0.535 |
| 50 % | 0.998 | 0.998 | 0.566 | 0.561 |

Overall ROC-AUC is 0.731 and balanced accuracy 0.694. Replacement is detected reliably from small payloads up. Matching stays close to chance at every payload, the known blind spot of statistical LSB detectors, and the reason matching is the default. Layout changes AUC by at most 0.07.

### 4.3 Pre-flight validity

| Predicted level | Actually detected (all covers) | Smooth covers | Textured covers |
|---|---|---|---|
| Low | **0.0 %** (n = 125) | 0.0 % (n = 77) | 0.0 % (n = 48) |
| Medium | 9.9 % (n = 384) | 8.0 % (n = 162) | 11.3 % (n = 222) |
| High | **99.3 %** (n = 291) | 100 % (n = 161) | 98.5 % (n = 130) |

There were 800 trials: real format-v2 messages at the four standard sizes, both algorithms. Predicted and actual probabilities agree closely (Spearman ρ = 0.98). The prediction is equally valid for smooth and textured covers. Contrary to the proposal's assumption, texture barely changes risk for this detector, because SPA measures embedding relative to each image.

### 4.4 Transport robustness

| Transport | Recovered | Failed safely | Unsafe |
|---|---|---|---|
| PNG re-save | 40 / 40 | 0 | 0 |
| JPEG quality 90 | 0 | 40 / 40 | 0 |
| JPEG quality 75 | 0 | 40 / 40 | 0 |
| Resize to 50 % | 0 | 40 / 40 | 0 |

The message survives lossless transport only. Every lossy trial failed safely, with no partial plaintext, no garbage output and no crash.

### 4.5 Security and integrity

All 32 security tests pass: bit flips in the packet or pixels, header tampering, wrong password, wrong private key, cropping, extraction with only the public key, password-guess cost, and a signature scan. The full automated suite has 157 Python tests (security, crypto, embedding, ML, experiments, API) and 22 front-end unit tests.

## 5. Limitations

- **LSB replacement is detectable.** Even 5 % payloads are caught most of the time (AUC 0.866). Matching evades *this* detector, but stronger detectors (e.g. CNN-based steganalysis) may not be fooled.
- **No robustness to lossy transport.** JPEG recompression or resizing destroys the message; it fails safely but can't be recovered. Images must travel as files, not as photos that a messaging app recompresses.
- **Detector scope.** The detector was trained on one image source (DIV2K, 512×512 PNG crops). Behaviour on other cameras, sizes or processing is unmeasured. Synthetic images (e.g. pure noise) are out of distribution.
- **Key encoding.** A valid X25519 public key is not a perfectly uniform bit string. Hiding that would need Elligator2 encoding. With one image this leaks at most about one bit of evidence.
- **Experiment variance.** The pre-flight and robustness experiments use the real pipeline, whose keys come from the operating system's random generator by design. Their individual scores vary slightly between runs; the quality and detector results are byte-identical.

## 6. Future work

- Adaptive, content-aware embedding (e.g. HUGO or WOW style costs) to lower detectability further.
- A CNN steganalyser, both as a stronger detector and to test whether matching remains hard to detect.
- JPEG-domain embedding, for messages that must survive recompression.
- Elligator2 encoding of the one-time public key.
- A wider detector training set (several cameras, sizes and post-processing pipelines).

## 7. Conclusion

StegoShield delivers the full pipeline the proposal set out: authenticated encryption, keyed embedding with nothing recognisable in the pixels, a calibrated detector, and a pre-flight check that uses the detector to advise the sender. The evaluation shows the pre-flight check is a dependable guide: a Low prediction was never detected in 125 trials. The main practical finding is that the embedding *algorithm* matters far more than the cover's texture. With LSB matching, messages stayed near-undetectable for this detector at every size tested.

## Appendix: reproducing the results

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python -m ml.prepare_covers && python -m ml.dataset   # covers + feature table (~17 min)
python -m ml.train_detector                            # optional: the trained model is committed
python -m experiments.quality && python -m experiments.detector_eval
python -m experiments.preflight_eval && python -m experiments.robustness && python -m experiments.security
pytest                                                 # automated tests
```

All scripts default to seed 2026. Results are written to `experiments/results/` and `docs/figures/`.
