# StegoShield

> **A smart web platform for encrypted steganography and AI-based steganalysis.**

StegoShield combines authenticated cryptography (**AES-256-GCM**, **PBKDF2**, and **X25519 ECDH**), keyed pseudorandom LSB steganography, a pre-flight cover image risk and capacity evaluator, and an AI-driven steganalysis detector into a unified dashboard.

---

## Architecture Overview

1. **Module A (Encryption & Key Management):**
   - Symmetric password mode (PBKDF2-HMAC-SHA256 + AES-256-GCM).
   - Asymmetric mode (X25519 ECDH + HKDF key exchange + AES-256-GCM).
2. **Module B (Pre-Flight Cover Image Checker & Risk Scoring):**
   - Exact carrier payload capacity calculation.
   - Machine learning risk score predicting detectability before embedding.
3. **Module C (Steganographic Embedding & Extraction):**
   - Cryptographically keyed pseudorandom LSB scattering across color channels.
   - Safe extraction failure and AES-GCM authentication verification against tampering.
4. **Module D (Defensive AI Steganalysis Detector):**
   - LSB-plane statistical variance, chi-square attack statistics, and spatial co-occurrence matrices.
   - Probability scoring for steganographic anomalies.

---

## Directory Structure

```
StegoShield/
├── core/                  # Cryptography, key exchange, and steganography primitives
│   ├── crypto.py          # AES-256-GCM, PBKDF2, and X25519 ECDH
│   ├── keys.py            # Keypair generation and import/export
│   ├── embed.py           # Keyed pseudorandom LSB embedding and extraction
│   ├── capacity.py        # Capacity calculation and safe payload thresholds
│   └── pipeline.py        # End-to-end encryption/embedding pipeline
├── ml/                    # Machine learning models and feature extraction
│   ├── features.py        # LSB statistics, chi-square, spatial co-occurrence
│   ├── dataset.py         # Stego-cover dataset generation
│   ├── detector.py        # Steganalysis detector inference
│   └── risk.py            # Pre-flight cover image risk scoring
├── tests/                 # Unit and security testing suite
│   ├── test_crypto.py     # Cryptography round-trip and tamper tests
│   ├── test_embed.py      # Embedding, extraction, and permutation tests
│   └── test_security.py   # Full security and tampering validation
├── data/                  # Local datasets and evaluation samples
├── models/                # Trained detector and risk models (.joblib)
├── notebooks/             # Google Colab training and experimentation notebooks
├── docs/                  # Architecture and protocol specifications
│   └── payload_format.md  # Binary payload specification
├── app.py                 # Streamlit multi-tab dashboard
├── requirements.txt       # Python dependencies
└── README.md              # Project documentation
```

---

## Local Setup

### 1. Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- Git

### 2. Create and Activate Virtual Environment
```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Test Suite
```bash
pytest
```

### 5. Launch Dashboard
```bash
streamlit run app.py
```

> **A smart web platform for encrypted steganography and AI-based steganalysis.**

StegoShield combines authenticated cryptography (**AES-256-GCM**, **PBKDF2**, and **X25519 ECDH**), keyed pseudorandom LSB steganography, a pre-flight cover image risk and capacity evaluator, and an AI-driven steganalysis detector into a unified dashboard.

---

## Architecture Overview

1. **Module A (Encryption & Key Management):**
   - Symmetric password mode (PBKDF2-HMAC-SHA256 + AES-256-GCM).
   - Asymmetric mode (X25519 ECDH + HKDF key exchange + AES-256-GCM).
2. **Module B (Pre-Flight Cover Image Checker & Risk Scoring):**
   - Exact carrier payload capacity calculation.
   - Machine learning risk score predicting detectability before embedding.
3. **Module C (Steganographic Embedding & Extraction):**
   - Cryptographically keyed pseudorandom LSB scattering across color channels.
   - Safe extraction failure and AES-GCM authentication verification against tampering.
4. **Module D (Defensive AI Steganalysis Detector):**
   - LSB-plane statistical variance, chi-square attack statistics, and spatial co-occurrence matrices.
   - Probability scoring for steganographic anomalies.

---

## Directory Structure

```
StegoShield/
├── core/                  # Cryptography, key exchange, and steganography primitives
│   ├── crypto.py          # AES-256-GCM, PBKDF2, and X25519 ECDH
│   ├── keys.py            # Keypair generation and import/export
│   ├── embed.py           # Keyed pseudorandom LSB embedding and extraction
│   ├── capacity.py        # Capacity calculation and safe payload thresholds
│   └── pipeline.py        # End-to-end encryption/embedding pipeline
├── ml/                    # Machine learning models and feature extraction
│   ├── features.py        # LSB statistics, chi-square, spatial co-occurrence
│   ├── dataset.py         # Stego-cover dataset generation
│   ├── detector.py        # Steganalysis detector inference
│   └── risk.py            # Pre-flight cover image risk scoring
├── tests/                 # Unit and security testing suite
│   ├── test_crypto.py     # Cryptography round-trip and tamper tests
│   ├── test_embed.py      # Embedding, extraction, and permutation tests
│   └── test_security.py   # Full security and tampering validation
├── data/                  # Local datasets and evaluation samples
├── models/                # Trained detector and risk models (.joblib)
├── notebooks/             # Google Colab training and experimentation notebooks
├── docs/                  # Architecture and protocol specifications
│   └── payload_format.md  # Binary payload specification
├── app.py                 # Streamlit multi-tab dashboard
├── requirements.txt       # Python dependencies
└── README.md              # Project documentation
```

---

## Local Setup

### 1. Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- Git

### 2. Create and Activate Virtual Environment
```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Test Suite
```bash
pytest
```

### 5. Launch Dashboard
```bash
streamlit run app.py
```
