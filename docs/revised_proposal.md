# StegoShield
### A smart web platform for encrypted steganography and AI-based steganalysis
**Revised Project Proposal (Scoped)**

Ahmed Salman 23L-0678 (7J) · Alishba Jamal Uddin Ahmed 23L-1002 (7J) · Kashmala 23L-0878 (7J)
National University of Computer and Emerging Sciences, Lahore
Revised: November 26, 2026 (original: October 27, 2026)

---

## 1. Executive Summary

StegoShield is a Python web application for covert, end-to-end encrypted communication and defensive steganalysis. Encryption hides *what* is said but not *that* something secret is being said. StegoShield hides AES-256-GCM encrypted messages inside PNG images, scattering the bits across pixels at secret, key-derived positions. It also helps both sides of the problem:

- **Senders** get a *Pre-Flight Risk Check*. Before hiding anything, the system simulates the embedding and asks a trained ML detector how likely the result is to be caught.
- **Defenders** get an *AI Steganalysis Detector* that flags images likely to contain hidden data.

This revision narrows the scope so the full pipeline can be delivered, measured and demonstrated end to end. The core idea of the original proposal is unchanged.

## 2. Problem Statement & Motivation

In high-surveillance environments, visible ciphertext draws attention. Steganography hides the message inside an innocent-looking image, but current tools have three weaknesses:

1. **Poor image selection.** Smooth, low-texture images (e.g. clear skies) make pixel changes statistically obvious.
2. **Unknown safe capacity.** Users don't know how much data they can hide before detection becomes likely.
3. **No link between hiding and detecting.** Tools either hide or detect. They rarely use a detector to judge how safe an embedding is.

StegoShield addresses all three: it measures risk before embedding, hides data securely, and detects hidden data with ML.

## 3. Objectives & Scope

**In scope**
- **Authenticated encryption:** AES-256-GCM with a password (PBKDF2, 600,000 iterations) or an X25519 public key (ECDH + HKDF).
- **Keyed pseudorandom LSB embedding:** bit positions come from the *secret* key, and the embedded data contains no plaintext markers, so without the key it is indistinguishable from noise.
- **ML steganalysis detector:** a Random Forest trained on per-channel statistical features of clean and stego images.
- **Detector-in-the-loop pre-flight check:** risk score (Low/Medium/High) and a recommended safe payload size for a candidate cover image.
- **Streamlit dashboard** with five tabs: Keys, Pre-Flight Check, Hide & Extract, AI Detector, and an Evaluation Lab that runs the quality, robustness and attack tests live.

**Out of scope for this project**
- CNN / deep-learning detectors (Random Forest only).
- A separately trained risk *regression* model. The detector itself is used to estimate risk (see Module B).
- Testing on real social-media platforms. JPEG recompression and resizing are simulated locally instead.
- Adaptive embedding schemes (e.g. HUGO, WOW), JPEG-domain steganography, audio and video carriers.
- Public deployment and user accounts.

## 4. Technical Methodology

### Module A: Encryption & Key Management
- **Password mode:** PBKDF2-HMAC-SHA256 with a random salt derives a master key. HKDF splits it into an encryption key and a separate pixel-position key.
- **Public-key mode:** the sender creates a one-time X25519 keypair. The ECDH shared secret is passed through HKDF to get the encryption and position keys.
- The format header is authenticated by AES-GCM (as Additional Authenticated Data), so any tampering is detected.

### Module B: Pre-Flight Cover Image Check
- **Capacity:** the exact maximum payload in bytes, from image size and channels, including encryption overhead.
- **Detector-in-the-loop risk score:** the system hides random data of the planned size in a copy of the cover image, runs the Module D detector on it, and reports the detection probability as the risk score (Low < 35% ≤ Medium ≤ 65% < High).
- **Recommended safe payload:** the largest tested payload ratio (5%, 10%, 25%, 50%) whose simulated risk stays *Low*.

### Module C: Steganographic Embedding & Extraction
- The encrypted payload is embedded in the least significant bits of the R, G and B channels. Positions are chosen by a pseudorandom generator seeded with the secret key.
- **Two-stage layout:** a random value (the salt, or the one-time public key) is stored first, and the rest of the payload goes to positions that only the key holder can compute. The length field is masked.
- Two embedding options: **LSB replacement** and **LSB matching (±1)**. A **sequential** mode is kept only as a baseline for comparison.
- A wrong key or a tampered image fails safely with an authentication error, never with garbage output.

### Module D: AI Steganalysis Detector
- **Dataset:** about 500 natural PNG cover images (512×512 crops from the DIV2K dataset), each embedded at 5%, 10%, 25% and 50% payload. The train/test split is by cover image, so no image appears in both.
- **Features:** computed per colour channel. LSB-plane statistics, chi-square (pairs-of-values) test, neighbouring-pixel difference statistics, co-occurrence statistics, and texture/edge complexity.
- **Model:** Random Forest classifier with calibrated probabilities. The output is the probability that an image contains hidden data, plus the features that contributed most.

## 5. Evaluation Plan

| Experiment | Measure | Conditions |
|---|---|---|
| Visual quality | PSNR, SSIM | 5 / 10 / 25 / 50% payload |
| Detector performance | Accuracy, Precision, Recall, ROC-AUC | Sequential vs pseudorandom; replacement vs matching; per payload ratio |
| Pre-flight validity | Does a "Low" risk prediction match a low actual detection rate? | Smooth vs textured covers |
| Transport robustness | Extraction success rate | Lossless PNG re-save vs JPEG (quality 90, 75) vs 50% resize |
| Security & integrity | Safe failure | Bit-flips, header tampering, wrong key, cropping, keyless extraction attempts |

## 6. Deliverables
1. Working Streamlit app (five tabs, including the Evaluation Lab) and command-line tool.
2. Trained detector model (`models/detector.joblib`).
3. Experiment scripts with results tables and figures (PSNR/SSIM, ROC, robustness).
4. Automated test suite, including the security tests.
5. Short final report and live demo.
