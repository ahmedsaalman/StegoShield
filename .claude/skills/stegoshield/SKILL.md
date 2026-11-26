---
name: stegoshield
description: Project rules for StegoShield (encrypted LSB steganography + Random Forest steganalysis; Python core, FastAPI back end, React + TypeScript front end). Use for ANY work in this repo — writing or reviewing code in core/, ml/, api/, frontend/, experiments/ or tests/; designing or changing pages, flows or copy; planning or closing a phase from docs/phases.md; or rating code quality. Covers phase workflow, security and ML invariants, Python and TypeScript clean-code standards, testing, and web UX/accessibility.
---

# StegoShield Project Skill

StegoShield hides AES-256-GCM encrypted messages in PNG pixels at key-derived positions, warns senders how detectable an embedding will be, and detects hidden data with a Random Forest. Read this whole file before writing code or UI for the project.

## 0. Before you start any task

1. **Find the phase.** Open [docs/phases.md](../../../docs/phases.md) and identify which phase the task belongs to. Work only within that phase's tasks; if the request falls outside it, say so before proceeding.
2. **Check scope.** [docs/revised_proposal.md](../../../docs/revised_proposal.md) §3 lists what is *out of scope*: CNN detectors, a separate risk regressor, adaptive embedding (HUGO/WOW), JPEG-domain stego, audio/video, real social-media tests, public deployment, user accounts. (Docker packaging for self-hosting is in scope.) Do not build these, even partially.
3. **Read before changing.** Read the module you are about to touch and its tests. Match existing conventions unless this file says otherwise.
4. **Decide the deliverable type** (code, test, UI change, doc, review) and jump to the matching section below.

## 1. Project map

| Module | Purpose | Files |
|---|---|---|
| A: Encryption & keys | AES-256-GCM; PBKDF2 (600k) password mode; X25519 + HKDF public-key mode | `core/crypto.py`, `core/keys.py` |
| B: Pre-flight check | Capacity, detector-in-the-loop risk, safe payload | `core/capacity.py`, `ml/risk.py` |
| C: Embedding | Keyed pseudorandom LSB replacement / matching (±1); sequential = baseline only | `core/embed.py`, `core/pipeline.py` |
| D: Detector | Per-channel statistical features → calibrated Random Forest | `ml/features.py`, `ml/dataset.py`, `ml/detector.py` |
| API | Stateless FastAPI REST layer; the only code that touches HTTP | `api/` (`api/analysis.py` is the sole adapter to `ml/`) |
| UI | React + TypeScript single-page app (Vite) | `frontend/src/` (`pages/`, `components/`, `lib/api.ts`, `styles.css`) |
| Legacy | Old Streamlit dashboard, to be deleted at the end of Phase 6 | `app.py` (don't extend it) |
| Evaluation | Quality, detector, pre-flight validity, robustness | `experiments/`, `docs/results.md` |

Domain exceptions (use these; add new ones to the same hierarchy):
`StegoCryptoError` → `AuthenticationError`, `InvalidPayloadError` (in `core/crypto.py`); `CapacityExceededError(ValueError)` (in `core/capacity.py`).

Commands: `make check` (all lint + tests) · `make dev-api` + `make dev-web` (hot reload) · `make serve` (production-style) · `.venv/bin/python -m pytest -q` · `npm --prefix frontend test` · `python -m core.pipeline --help`

## 2. Security invariants (non-negotiable)

Breaking any of these is a blocker regardless of how clean the code is.

1. **Fail closed.** Wrong key, flipped bit, tampered header, or cropped image must raise `AuthenticationError` or `InvalidPayloadError`. Never return partial plaintext, garbage, or `None`.
2. **No plaintext markers in pixels** (format v2+). Magic bytes, version, and mode live only in AES-GCM AAD. The length field is masked. Stored X25519 public keys get a randomised top bit.
3. **No cheap password oracle.** Nothing embedded may let an attacker reject a wrong password without paying the full PBKDF2 cost.
4. **Randomness.** Secrets, salts, nonces, and ephemeral keys come from `os.urandom` / `secrets` / `cryptography`. NumPy RNGs are used only for pixel positions and ±1 decisions, and only when **seeded from key-derived bytes**. Never use the `random` module or a fixed seed in production paths.
5. **Key separation.** Every derived key uses HKDF with its own `info=b"stegoshield-…"` label. Never reuse a key for two purposes.
6. **Constants are fixed.** Never lower `PBKDF2_ITERATIONS` or change nonce/tag sizes. If tests need speed, add a parameter with the production value as the default.
7. **No secret leakage.** Do not log, print, or put into exception messages or API error bodies: passwords, private keys, derived keys, or plaintext (other than returning the user their own decrypted message). API validation errors name the field, never the submitted value. Never store secrets in `localStorage`/`sessionStorage`; keep them in React state only.
8. **Format changes travel together.** Any change to the byte layout updates `docs/payload_format.md`, bumps the version constant, and adds or updates tests in `tests/test_security.py` in the same commit.
9. **Stateless server.** The API writes nothing to disk or a database. No accounts. Responses under `/api` are `Cache-Control: no-store`. Wrong key, tampering and "no message" return the same `no_message_found` error.

## 3. ML invariants

1. **Split by cover.** Train/test splits group by `cover_id`. A cover and its stego variants never appear on both sides. Keep a test asserting this.
2. **Never tune on the test set.** Use validation folds inside the training split.
3. **One feature order.** `ml/features.FEATURE_NAMES` is the single source of truth. Model artifacts store their `feature_names`; loading rejects a mismatch.
4. **Reproducible.** Every script takes `--seed` (default fixed) and writes it into its output.
5. **Calibrated probabilities.** The detector's output is used as a risk probability, so it must be calibrated (`CalibratedClassifierCV`).
6. **No silent fallbacks.** If the model file is missing, raise a clear error the UI can show. Do not substitute a heuristic and present it as a model score.
7. **Data stays out of git.** Never commit cover images, stego images, or feature CSVs.

## 4. Clean code standards

Code is read far more than it is written; optimise for the reader. Leave every file you touch a little cleaner (Boy Scout Rule), but **never refactor and add features in the same commit**.

### 4.1 Names
- Intention-revealing: `payload_ratio`, `stego_image`, `recipient_public_key`. Not `r`, `img2`, `pk`.
- Booleans read as predicates: `is_trained`, `has_capacity`, `should_mask_length`.
- Functions are verbs: `compute_payload_ratio()`, `extract_lsb_features()`. Classes are nouns: `StegoDetector`, `PreflightResult`.
- One word per concept across the codebase: *cover* (never also "carrier image" in code), *stego image*, *payload*, *embed / extract*, *detect*. Pick `load_` for disk reads and don't mix with `read_`/`fetch_`.
- Constants: `ALL_CAPS` at module top with units in the name when relevant: `RISK_LOW_THRESHOLD = 0.35`, `MAX_COVER_PIXELS`, `PAYLOAD_RATIOS = (0.05, 0.10, 0.25, 0.50)`.
- `snake_case` for functions and variables, `PascalCase` for classes (PEP 8).

### 4.2 Functions
- Do one thing at one level of abstraction; aim for under 20 lines. Extract named helpers instead of writing comments.
- Step-down rule: public entry points at the top of the module, helpers below in calling order.
- 0–2 arguments ideal, 3 needs a reason. Group related arguments in a `@dataclass` (e.g. `EmbedOptions(algorithm, layout)`).
- No boolean flag arguments that switch behaviour; use an `Enum` (`Algorithm.REPLACEMENT`, `Algorithm.MATCHING`) or two functions.
- Command–query separation: a function either returns a value or changes state.
- Guard clauses first, then one happy path. Avoid nesting deeper than 2.
- Full type hints on every public function; keep `from __future__ import annotations`.

### 4.3 Comments, docstrings, formatting
- Comments explain **why** (e.g. `# RFC 7748: receivers mask the top bit, so it is free to randomise`), never **what**.
- Every public function and class has a one-line docstring, plus `Raises:` when it raises domain exceptions.
- No commented-out code, no changelogs in files, no task IDs like "L20" in new docstrings; git keeps history.
- Formatting is `ruff format`; lint is `ruff check`. Don't hand-format.
- Use `pathlib.Path` for file paths, not string concatenation.

### 4.4 Error handling
- Raise domain exceptions with context: `CapacityExceededError(f"Payload needs {needed} bytes but cover holds {capacity} bytes")`.
- Catch specific exceptions only. No bare `except:` and no `except Exception` in `core/` or `ml/`. The UI layer may catch broadly only to show a friendly message, and must still handle the domain exceptions explicitly first.
- Wrap third-party errors at the boundary (e.g. `InvalidTag` → `AuthenticationError ... from e`).
- Don't return `None` to signal failure. Raise, or return an empty collection or a result object.
- Validate inputs at public entry points and fail fast (`ValueError` for empty password or plaintext).

### 4.5 Structure
- Layering: `core/` ← `ml/` ← `api/` ← `frontend/` (over HTTP). `core/` imports neither scikit-learn nor FastAPI. `api/` contains no crypto, embedding or feature logic; it validates, calls, and maps results/errors. Only `api/analysis.py` knows the shape of `ml/` results.
- New domain failures get a stable error `code` in `api/errors.py` (or an `ApiError`) and a title in `frontend/src/components/ErrorAlert.tsx`.
- CPU-heavy work in routes goes through `run_cpu_bound` (bounded pool), never directly in `async def`.
- `experiments/` code is importable; the Evaluation Lab page reuses it through the API rather than copying it.
- Magic numbers become named constants. Duplication at three occurrences becomes a helper.
- Return structured results (`@dataclass(frozen=True)`) instead of loose dicts for anything with more than about 3 fields.

### 4.6 TypeScript / React
- Strict TypeScript (`noUncheckedIndexedAccess`), no `any`. API types live in `frontend/src/lib/api.ts` and mirror `api/schemas.py`; change both together.
- All server calls go through `api.*` in `lib/api.ts`; components never call `fetch` directly. Async state uses `useRequest` (aborts stale requests).
- Pure logic (validation, formatting, labels) lives in `lib/` as plain functions with unit tests; components stay presentational.
- Function components and hooks only. Respect the `react-hooks` lint rules (no setState in effects, no ref reads during render).
- Styling uses the tokens in `styles.css` (colour, spacing, radius, type scale). No inline colours, no per-component CSS files, no UI library.

## 5. Testing

- **pytest**, files `tests/test_<module>.py`. Names describe behaviour: `test_extract_raises_authentication_error_when_password_is_wrong`.
- API: `tests/test_api.py` with FastAPI's `TestClient` (use `with TestClient(...)` so the lifespan runs). Prefer public-key mode in API tests; password mode costs a full PBKDF2 run.
- Front end: Vitest + Testing Library, files next to the code (`*.test.ts(x)`). Query by role and label text, as a user would; mock `fetch`, not modules.
- Arrange–Act–Assert, one concept per test. Use `@pytest.mark.parametrize` for ratio, mode, and algorithm grids.
- Every attack or failure mode in §2 has a test in `tests/test_security.py`; every new public function has a happy-path and a failure-path test.
- Tests are deterministic (fixed seeds, small synthetic images built in fixtures; no network, no DIV2K).
- The default suite stays under 10 s. Anything slower gets `@pytest.mark.slow`.
- When fixing a bug, write the failing test first.

## 6. UI/UX for the web app

### 6.1 Who uses it

| Persona | Goal | Main pages |
|---|---|---|
| **Sender** | Hide a message safely in a cover image | Pre-flight check, Hide a message, Keys |
| **Recipient** | Recover the message with their key | Reveal a message, Keys |
| **Defender / analyst** | Check whether an image hides data | Detect hidden data |
| **Evaluator** (examiner, demo audience) | See that the claims hold | Evaluation Lab (Phase 6) |

Platform: responsive web, desktop-first, must work at 390 px wide with no horizontal scroll (sidebar collapses to a top bar + menu below 900 px). Users are technical but **not** cryptographers: explain terms in plain words.

### 6.2 Visual language (Geist-inspired, chosen 26 Nov 2026)
- Near-monochrome: `--fg`/`--bg` plus greys. Colour only for status (success/info/warning/danger), always with words.
- 1px `--border` lines, no drop shadows. Radii 6 / 8 / 12 px.
- Geist Sans for interface text (14px base, 16px for inputs on touch); Geist Mono for numbers, sizes, fingerprints, step labels ("STEP 01") and eyebrows. Headings semibold with tight negative tracking.
- Shell: sticky top header (brand + version) with a tab row underneath; footer holds privacy note, detector status dot and the theme switcher. No sidebar.
- Primary buttons are solid `--button-bg` (black in light, white in dark); secondary are outlined; ghost for low-emphasis actions.
- Don't copy Vercel branding (logo, name, exact product copy); take the language, not the identity.
- Illustrations are inline SVG in `components/illustrations/`, drawn with `currentColor` and the scene tokens so they follow the theme, and always `aria-hidden`. No raster images or external image hosts (CSP allows only same-origin).
- Motion: animate only `transform`/`opacity` (plus `stroke-dashoffset` for line drawing), ease-out, ≤ 800ms for UI (ambient hero loops may be longer). Put every animation inside `@media (prefers-reduced-motion: no-preference)`; the static design must be complete without it. Animated numbers (`useCountUp`) are `aria-hidden` with the final value in visually-hidden text.

### 6.3 Page contract
Navigation is grouped by goal: **Send** (Pre-flight check, Hide) → **Receive** (Reveal) → **Analyse** (Detect) → **Set up** (Keys). Each page has:
- A `PageHeader` band (mono eyebrow, one `h1`, one sentence; it also sets `document.title`), then content inside `PageBody` (`isNarrow` for forms: 800px, same left edge as the title).
- Sections are `Card`s: optional mono `step` label, title, description, body, and a grey footer bar for hints, counters and the card's action.
- **One primary action** (`<Button variant="primary">`); everything else is secondary or ghost.
- Inputs above, results below, in the order the user acts. Multi-step forms use numbered `card` sections.
- All five states designed and implemented:

| State | Pattern |
|---|---|
| Empty | `FileDrop` or field with a short instruction, e.g. "Choose an image or drag it here" |
| Loading | Button `isLoading` + specific `loadingLabel` ("Encrypting and hiding…") |
| Success | `Alert tone="success" live` + the result + the next step |
| Error | `ErrorAlert` (titled by error `code`, server message, recovery tips). Never a stack trace. |
| Not ready | e.g. detector not installed: `Alert tone="info"` saying what is unavailable and why |

### 6.4 Content and copy
- Every API error `code` maps to a human title in `ErrorAlert`; the server's `message` says what to do.
- Validate in the browser first (types, sizes, required fields, password confirmation) and show field errors next to the field; the server re-validates everything.
- Numbers carry units and sensible precision via `lib/format.ts`: "12.2 KB", "18%", "64 × 64 px".
- Warn before risky actions: JPEG covers, sequential layout, downloading a private key, sending the result as a photo.

### 6.5 Secrets in the UI
- Passwords and passphrases use `PasswordInput` (masked, with a show/hide toggle and correct `autoComplete`).
- Secrets live only in component state; a saved recipient *public* key may live in `AppState` (memory) for the session. Nothing secret in browser storage.
- Private-key downloads carry the warning "Anyone with this file can read messages sent to you." Offer "Clear from screen" for keys and revealed messages.

### 6.6 Accessibility (required, enforced by `eslint-plugin-jsx-a11y` strict)
- **Never use colour alone.** Status uses `StatusBadge`: icon + words + number (`Low risk · 18%`).
- Text contrast ≥ 4.5:1 in both themes; only use colour tokens from `styles.css`, which are checked for both.
- Every control has a visible `<label>`; hints and errors are linked with `aria-describedby` (use `Field`). Radio choices use `ChoiceGroup` (native radios in a `fieldset`/`legend`).
- File pickers are real `<input type="file">` (`FileDrop`); drag-and-drop is an extra.
- Focus is always visible; after navigation focus moves to the page `h1`; there is a skip link; touch targets ≥ 44 px.
- Results and errors are announced (`role="status"` / `role="alert"`). Scrollable regions are focusable with a label.
- Respect `prefers-reduced-motion`; no autoplaying animation.

### 6.7 Design workflow
```
Exploring layout or flow?        → text/ASCII wireframe in chat, agree before coding
Flow across pages?               → Mermaid diagram (docs/ or chat)
Agreed design?                   → implement with the existing components and tokens
Comparing options?               → two variants side by side in chat, with trade-offs
```
After implementing, run `make serve` (or `make dev-api` + `make dev-web`) and check the page in all five states, in light and dark themes, at desktop width and at 390 px. For changes based on feedback, list the requested changes first, then state the trade-offs you made.

## 7. Done checklist (run before every commit)

- [ ] Task belongs to the current phase in `docs/phases.md`; phase status updated if a phase closed
- [ ] §2 security invariants and §3 ML invariants hold
- [ ] `make check` green: pytest (< 10 s, no new warnings), ruff, ESLint, TypeScript, Vitest; new code has success and failure tests
- [ ] UI changes: all five states shown, light + dark, 390 px wide, no colour-only signals, no stack traces, walkthrough done
- [ ] Related docs updated in the same commit
- [ ] Commit message `phase N: <what changed>`; no refactor mixed with feature work

## 8. Reviewing code: score 0–10

When asked to review or rate code, give a score, then the specific changes needed to reach 10.

| Score | Meaning |
|---|---|
| 9–10 | Invariants hold; names reveal intent; small focused functions; specific exceptions; clean, complete tests including failure paths |
| 7–8 | Mostly clean; minor naming issues or a few long functions; tests miss some edge cases |
| 5–6 | Mixed: some duplication, loose dicts, inconsistent errors, business logic leaking into `api/` routes or React components |
| 3–4 | Long multi-purpose functions, misleading names, missing failure tests |
| 0–2 | Works but unreadable, or **any security invariant broken** (caps the score at 2) |

Order findings: security → correctness → ML leakage → tests → design/clean code → UX → style. Cite `file:line` for each.
