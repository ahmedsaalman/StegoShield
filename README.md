# StegoShield

> **A smart web platform for encrypted steganography and AI-based steganalysis.**

StegoShield combines authenticated cryptography (**AES-256-GCM**, **PBKDF2**, and **X25519 ECDH**), keyed pseudorandom LSB steganography, a pre-flight cover image risk and capacity evaluator, and an AI-driven steganalysis detector into one web application: a **React + TypeScript** front end on a stateless **FastAPI** back end.

---

## Architecture Overview

1. **Module A (Encryption & Key Management):**
   - Symmetric password mode (PBKDF2-HMAC-SHA256 + AES-256-GCM).
   - Asymmetric mode (X25519 ECDH + HKDF key exchange + AES-256-GCM).
2. **Module B (Pre-Flight Cover Image Checker & Risk Scoring):**
   - Exact message capacity, including the format v2 overhead for the chosen key mode.
   - Detector-in-the-loop risk: random bytes of the planned size are hidden in a copy of the cover and the trained detector scores it (Low < 35% ≤ Medium ≤ 65% < High).
   - Recommended safe size: the largest of {5, 10, 25, 50 %} of the cover (or the planned size) that scores Low.
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
│   ├── train_detector.py  # Source-grouped split, calibrated Random Forest, held-out metrics
│   └── risk.py            # Pre-flight check: capacity + detector-in-the-loop risk
├── experiments/           # Reproducible evaluations (quality, detector, pre-flight, robustness, security)
│   └── results/           # CSV outputs + split.csv (which covers are held out)
├── api/                   # FastAPI back end (stateless REST API over core/ and ml/)
│   ├── main.py            # App factory, middleware stack, serves the built front end
│   ├── routes/            # /api/keys, /api/hide, /api/reveal, /api/capacity, /api/preflight, /api/detect
│   ├── analysis.py        # The only adapter between the API and ml/
│   ├── images.py          # Upload limits, format checks, safe decoding
│   ├── middleware.py      # Security headers, rate limit, body-size limit, request IDs
│   └── errors.py          # One JSON error shape; never echoes secrets
├── frontend/              # React + TypeScript + Vite single-page app
│   └── src/               # pages/, components/, lib/ (typed API client), styles.css (design tokens)
├── tests/                 # Unit and security testing suite
│   ├── test_crypto.py     # Cryptography round-trip and tamper tests
│   ├── test_embed.py      # Embedding, extraction, and permutation tests
│   └── test_security.py   # Full security and tampering validation
├── data/                  # Local datasets and evaluation samples
├── models/                # Trained detector (.joblib) and its held-out metrics
├── notebooks/             # Google Colab training and experimentation notebooks
├── docs/                  # Architecture and protocol specifications
│   ├── payload_format.md  # Binary payload specification
│   ├── results.md         # Evaluation results: tables, figures, interpretation
│   └── figures/           # Experiment figures (PNG)
├── Dockerfile             # Single production image: API + built front end
├── requirements.txt       # Python dependencies
└── README.md              # Project documentation
```

---

## Local Setup

### 1. Prerequisites
- Python 3.12
- Node.js 22.12+ (front end)
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
pip install -r requirements-dev.txt   # app + pytest + ruff
npm --prefix frontend ci              # front end (exact versions from package-lock.json)
```

### 4. Run Tests and Lint
```bash
make check        # everything below
pytest            # Python: fast suite (slow tests: pytest -m slow)
ruff check .
npm --prefix frontend test            # front end: Vitest + Testing Library
npm --prefix frontend run lint        # ESLint incl. jsx-a11y accessibility rules
npm --prefix frontend run typecheck
```

### 5. Run the Web App
**Development** (two terminals, hot reload):
```bash
make dev-api      # FastAPI on http://127.0.0.1:8000 (API docs at /api/docs)
make dev-web      # React on http://localhost:5173, proxies /api to :8000
```
**Production-style** (one process, one origin):
```bash
make serve        # builds frontend/dist, then serves API + app on http://127.0.0.1:8000
```
**Docker:**
```bash
docker build -t stegoshield .
docker run -p 8000:8000 stegoshield
```
If `models/detector.joblib` is missing or was trained on a different feature set, the app still runs; `/api/meta` reports why and the Detect page explains that scanning is unavailable.

**Hosted demo (Oracle Cloud Always Free):** the examiners' link. A small ARM VM runs the same image behind [Caddy](https://caddyserver.com), which fetches and renews a Let's Encrypt certificate. The free `<ip-with-dashes>.sslip.io` hostname means no domain is needed. Files: `deploy/oracle/` (`compose.yaml`, `Caddyfile`, `setup.sh`, `update.sh`).

One-time setup:
1. **Oracle console:** create an instance: *Ubuntu 24.04*, shape *VM.Standard.A1.Flex* (1 OCPU / 6 GB is plenty), a public IPv4 address, and your SSH public key. In the instance's subnet → *Security List*, add ingress rules for TCP 80 and TCP 443 from `0.0.0.0/0`.
2. **Deploy key, on your machine:** `ssh-keygen -t ed25519 -N "" -C stegoshield-deploy -f ~/.ssh/stegoshield_deploy`
3. **On the VM** (`ssh ubuntu@<ip>`):
   ```bash
   curl -fsSL https://raw.githubusercontent.com/ahmedsaalman/StegoShield/main/deploy/oracle/setup.sh -o setup.sh
   DEPLOY_PUBLIC_KEY="<contents of ~/.ssh/stegoshield_deploy.pub>" bash setup.sh   # ~10 min: Docker, firewall, first build
   ```
   It prints the live URL. The VM's own iptables rules are opened too: Oracle's Ubuntu images block everything except SSH.
4. **GitHub** → Settings → Secrets and variables → Actions:
   - variable `ORACLE_HOST` = the VM's IP;
   - secret `ORACLE_SSH_KEY` = contents of `~/.ssh/stegoshield_deploy`;
   - secret `ORACLE_KNOWN_HOSTS` = output of `ssh-keyscan -t ed25519 <ip>`.

From then on, `.github/workflows/deploy.yml` runs the Python and front-end tests on every push to `main` that touches the app. If they pass, it SSHes in, and `update.sh` resets the VM to `origin/main`, rebuilds, and waits for the container's health check. The deploy key can only run `update.sh`, because it carries a forced command in `authorized_keys`. Until `ORACLE_HOST` is set, the deploy job is skipped. To redeploy without a push, use Actions → *Deploy to Oracle Cloud* → *Run workflow*.
- The app port (8000) is never published; only Caddy reaches it. That's why `FORWARDED_ALLOW_IPS=*` is safe there: Caddy overwrites any `X-Forwarded-For` a client sends, so rate limits apply per visitor. HSTS is on, and heavy jobs are capped at 2.
- Visitors' passwords and private keys reach the server. It stores nothing, but treat the demo as a demo: use test secrets.

### 6. Build the Detector Dataset
```bash
python -m ml.prepare_covers   # downloads DIV2K valid + train if missing (~4 GB), cuts 2,100 covers into data/covers/
python -m ml.dataset          # 2,100 clean + 33,600 stego rows x 258 features -> data/features/features.csv (~65 min on 7 cores)
```
Covers come from 900 DIV2K photos: the 100 validation photos (5 crops each) and the 800 training photos (2 crops each). `--sets valid` rebuilds only the original 500 covers. Both scripts take `--seed` (default 2026); the same seed gives a byte-identical CSV. Data folders are git-ignored.

### 7. Train the Detector
```bash
python -m ml.train_detector   # -> models/detector.joblib + models/detector_metrics.json (~20 min)
```
Splits train/test by source photo (80/20), so no photo's crops appear on both sides, then picks the forest's per-split feature share and the calibration method by grouped cross-validation on the training split, and fits a calibrated Random Forest. `models/detector_metrics.json` has held-out ROC-AUC overall and per ratio, layout and algorithm. The trained model is committed, so the app works without this step.

### 8. Run the Experiments
```bash
python -m experiments.quality          # PSNR / SSIM per payload ratio
python -m experiments.detector_eval    # ROC curves + metrics per ratio, layout, algorithm
python -m experiments.preflight_eval   # predicted risk vs actual detection, smooth vs textured
python -m experiments.robustness       # PNG / JPEG / resize transport
python -m experiments.security         # security test outcomes
```
Each script uses only the detector's held-out covers, takes `--seed`, and writes `experiments/results/*.csv` and `docs/figures/*.png`. Results and interpretation: [docs/results.md](docs/results.md).


---

## Web API

All endpoints live under `/api`; interactive documentation is at `/api/docs`. Uploads are `multipart/form-data`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness probe |
| GET | `/api/meta` | Version, upload limits, detector status |
| POST | `/api/keys/generate` | New X25519 key pair (optional passphrase on the private key) |
| POST | `/api/keys/inspect` | Validate a public key and return its fingerprint |
| POST | `/api/capacity` | Largest message an image can hold, per protection method |
| POST | `/api/preflight` | Capacity + detectability risk for a planned message size |
| POST | `/api/hide` | Encrypt and hide a message; returns a PNG |
| POST | `/api/reveal` | Verify and decrypt a hidden message |
| POST | `/api/detect` | Probability that an image hides data, with top contributing features |
| GET | `/api/lab/results` | Evaluation Lab: headline numbers from the saved held-out experiment runs |
| POST | `/api/lab/quality` | Evaluation Lab: PSNR / SSIM of the upload at 5–50 % payload, both algorithms |
| POST | `/api/lab/robustness` | Evaluation Lab: does a hidden message survive PNG re-save, JPEG q90/q75, 50 % resize |
| POST | `/api/lab/attacks` | Evaluation Lab: wrong keys, bit flips, cropping, signature scan against a real message |
| POST | `/api/lab/detector-comparison` | Evaluation Lab: detector score clean vs replacement vs matching at 5–50 % |

Every error has the same shape: `{"error": {"code", "message", "field?", "request_id"}}`. A wrong key, a modified image and "no message" all return the same `no_message_found` error on purpose.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `STEGOSHIELD_MAX_UPLOAD_MB` | 10 | Largest accepted image file |
| `STEGOSHIELD_MAX_IMAGE_PIXELS` | 16777216 | Largest image (width × height), checked before decoding |
| `STEGOSHIELD_MAX_MESSAGE_BYTES` | 524288 | Largest message accepted by `/api/hide` |
| `STEGOSHIELD_RATE_LIMIT_PER_MINUTE` | 60 | POST requests per client IP per minute, per worker (0 disables) |
| `STEGOSHIELD_MAX_CONCURRENT_JOBS` | CPU count | CPU-heavy jobs run at once per worker |
| `STEGOSHIELD_CORS_ORIGINS` | *(none)* | Comma-separated origins; only needed if the front end is hosted elsewhere |
| `STEGOSHIELD_STATIC_DIR` | `frontend/dist` | Built front end to serve; empty to serve the API only |
| `STEGOSHIELD_DETECTOR_PATH` | `models/detector.joblib` | Trained detector artifact |
| `STEGOSHIELD_ENABLE_DOCS` | 1 | Serve `/api/docs` |
| `STEGOSHIELD_ENABLE_HSTS` | 0 | Send HSTS; enable only when served over HTTPS |
| `STEGOSHIELD_LOG_LEVEL` | INFO | Python log level |

### Security model

- **Stateless.** Nothing is written to disk or a database. Images, messages, passwords and keys exist only in memory for the duration of one request.
- **The server is trusted.** Encryption runs server-side, so the server sees the password or private key while handling a request. Run it yourself (localhost, or your own host behind HTTPS) rather than trusting someone else's instance.
- **No secret leakage.** Logs contain method, path, status, timing and a request ID only. Validation errors never echo submitted values. API responses are sent with `Cache-Control: no-store`.
- **Hardening.** Strict Content-Security-Policy, `X-Frame-Options: DENY`, `nosniff`, no referrer; per-IP rate limiting; request-size, file-size and pixel-count limits; a bounded worker pool for CPU-heavy jobs.
- **Output names don't leak.** The hidden-message PNG is named after the cover (`holiday.png`), not "stego".
