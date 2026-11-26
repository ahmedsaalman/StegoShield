# StegoShield: Live Demo Script

**Target length: 10 minutes + questions.** Adjust the timings to the slot you're given. Times in brackets are running totals.
**Flow:** keys → pre-flight → hide → reveal → detect → Evaluation Lab. One person drives, one narrates, one handles questions and the fallback.

Every "Expected" line below comes from a dry run on the demo cover (`0854_0`, a photo the detector never trained on).

---

## Before the day

1. **Build and start the app** on the presentation laptop:
   ```bash
   cd "IS PROJECT" && make install && make serve      # http://127.0.0.1:8000
   ```
   No network is needed after installation. Everything runs locally.
2. **Prepare the demo folder** (cover, message, and a pre-made LSB-replacement image for the detector contrast):
   ```bash
   mkdir -p ~/Desktop/stegoshield-demo
   cp data/covers/0854_0.png ~/Desktop/stegoshield-demo/cover.png
   .venv/bin/python - <<'EOF'
   from pathlib import Path
   from core.pipeline import stego_encode_password
   demo = Path.home() / "Desktop/stegoshield-demo"
   message = "Meet at the library at 5pm. Bring the notes. " * 190      # ~8.6 KB
   (demo / "message.txt").write_text(message)
   for algorithm in ("replacement", "matching"):
       stego = stego_encode_password(demo / "cover.png", message, "demo password 2026", algorithm=algorithm)
       stego.save(demo / f"stego-{algorithm}.png")
   EOF
   ```
3. **Record the fallback video** (macOS: ⌘⇧5 → Record Entire Screen). Run the whole script once at the planned pace and save it as `~/Desktop/stegoshield-demo/fallback.mov`. Keep it out of git.
4. **Rehearse twice, timed** (Phase 7 task). Note each run's time here: Run 1 ____ · Run 2 ____.

## 15 minutes before

- [ ] `make serve` is running. `http://127.0.0.1:8000/api/health` returns `{"status":"ok"}`.
- [ ] Browser at 125 % zoom, light theme, one tab, notifications off (Do Not Disturb).
- [ ] Finder window open on `~/Desktop/stegoshield-demo`, for drag-and-drop.
- [ ] Downloads folder empty, so the stego file is easy to find.
- [ ] `fallback.mov` opened in QuickTime and paused, in case it's needed.

---

## The demo

### 1. Opening (0:00 → 0:45)
**Say:** "Encryption hides *what* you say, but visible ciphertext shows *that* you're hiding something. StegoShield hides an encrypted message inside an ordinary photo. It also tells you, before you send it, how likely a detector is to notice."

Show the **Overview** page briefly.

### 2. Keys (0:45 → 1:45)
**Do:** **Keys** → **Generate key pair** (no passphrase) → **download the private key** into the demo folder.
**Say:** "This is X25519 public-key mode. The sender only needs my public key, and only my private key can open the message. Note the warning: anyone with this file can read my messages."
**Do:** copy the public key.

### 3. Pre-flight check (1:45 → 3:15)
**Do:** **Pre-flight** → drop `cover.png` → protection *Recipient's public key* → size **9000** bytes (about the size of `message.txt`) → **Run pre-flight check**.
**Expected:** **Low** risk (≈34 %); suggested maximum ≈49 KB.
**Say:** "This isn't a rule of thumb. The server hid 9 KB of random data in a copy of this photo, the way the real message will be hidden, and asked our trained detector to score it. Over 100 test photos, nothing rated Low was ever detected, and 99 % of High-rated messages were."

### 4. Hide (3:15 → 4:45)
**Do:** **Hide a message in this image** (or the **Hide** page with `cover.png`) → *Recipient's public key* → paste the public key → paste `message.txt` → leave **LSB matching (±1)** and **Scattered by key** → **Hide message** → **Download**.
**Expected:** "Your message is hidden", and a PNG download.
**Say:** "The image looks identical: PSNR above 54 dB even at 50 % payload. The pixels hold no header and no signature. Without the key, the bits are indistinguishable from noise."

### 5. Reveal (4:45 → 5:45)
**Do:** **Reveal** → drop the downloaded PNG → *My private key* → drop the private key file → reveal.
**Expected:** the original message.
**Say:** "Authenticated with AES-GCM. If even one bit had changed, or the key were wrong, you'd get 'no message found', the same answer as for an image with no message at all, so the error confirms nothing."

### 6. Detect (5:45 → 7:15)
**Do:** **Detect** → drop `stego-matching.png`.
**Expected:** ≈30–35 %, *Probably no hidden data* (varies slightly per run: the keys are random).
**Do:** drop `stego-replacement.png`: the same message hidden with LSB replacement.
**Expected:** 100 %, *Hidden data likely*. The top features are `spa_rate_*`.
**Say:** "Same message, same photo, different embedding algorithm. Replacement is caught every time. Sample Pairs Analysis sees the pairs of pixel values it creates. Matching nudges values up or down instead, and our detector can't tell it from a clean photo. That's why matching is the default."

### 7. Evaluation Lab (7:15 → 9:15)
> Depends on the Evaluation Lab page (Phase 6). If it's not ready, show `docs/results.md` and its figures instead.

**Do:** **Evaluation Lab** → saved results → upload `cover.png` → run the four demos:
- **Attacks:** the control is *Recovered*. Wrong password, wrong private key, bit flips, crop and signature scan all *Failed safely*.
- **Robustness:** PNG re-save *Recovered*. JPEG q90/q75 and resize *Failed safely*.
- **Detector comparison** (~5 s): replacement flagged from ~10 %, matching stays near the clean score.
- **Quality:** PSNR 64 → 54 dB from 5 % to 50 %.

**Say:** "These are the same experiment scripts that produced the report's numbers, running live on this photo."

### 8. Close (9:15 → 10:00)
**Say:** "Three findings. The pre-flight check is a reliable guide. The embedding algorithm matters far more than the photo. And every attack we tried fails safely. Limits: LSB doesn't survive JPEG, and a stronger CNN detector might catch matching. Both are in our future work."

---

## If something goes wrong

| Problem | Recovery (≤ 20 s) |
|---|---|
| Page won't load | Terminal: `make serve` again. If it fails a second time, switch to `fallback.mov` at the current step. |
| "Detector not available" | `models/detector.joblib` is missing or mismatched. Don't debug live; switch to the fallback video. |
| Upload rejected as too large | Use `cover.png` (512×512). Lab demos accept up to 1024×1024. |
| Reveal says "no message found" | Check the mode (*My private key* vs *Password*) and that the *downloaded* PNG was used, not `cover.png`. |
| Detector comparison is slow | It takes ~5 s; keep talking. The pre-flight and detector results above make the same point. |
| Laptop fails entirely | Play `fallback.mov` from a USB stick or a phone, and narrate over it. |

## Likely questions

- **"Why not just encrypt?"** Ciphertext is visible and attracts attention. Steganography hides that a message exists at all.
- **"Can the recipient's public key find the message?"** No. It only locates a random one-time key. The message positions need the private key.
- **"Can you brute-force the password offline?"** Every guess costs a full PBKDF2 run (600,000 iterations, ≈230 ms). Nothing embedded allows a cheaper check.
- **"Does it survive WhatsApp?"** No. Recompression destroys LSBs, and the app warns about this. It fails safely: no partial or wrong message.
- **"Why a Random Forest, not a CNN?"** Scope. It's interpretable (top features per image) and fast (< 1 s per image). A CNN is future work.
- **"Was the detector tested on its own training data?"** No. The split is by source photo, and every experiment re-checks that its covers are held out.
