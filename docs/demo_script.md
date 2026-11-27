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
2. **Prepare the demo folder** (cover, a ~3.8 KB message to hide live, and pre-made ~8.6 KB replacement/matching images for the detector contrast):
   ```bash
   mkdir -p ~/Desktop/stegoshield-demo
   cp data/covers/0854_0.png ~/Desktop/stegoshield-demo/cover.png
   .venv/bin/python - <<'EOF'
   from pathlib import Path
   from core.pipeline import stego_encode_password
   demo = Path.home() / "Desktop/stegoshield-demo"
   line = "Meet at the library at 5pm. Bring the notes. "
   (demo / "message.txt").write_text(line * 85)                    # ~3.8 KB: rated Low, hidden live
   contrast = line * 190                                           # ~8.6 KB: for the detector contrast
   for algorithm in ("replacement", "matching"):
       stego = stego_encode_password(demo / "cover.png", contrast, "demo password 2026", algorithm=algorithm)
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
**Do:** **Pre-flight** → drop `cover.png` → protection *Recipient's public key* → size **9000** bytes → **Run pre-flight check**.
**Expected:** **Medium** risk (≈45 %), suggested maximum ≈4,850 bytes.
**Do:** change the size to **4000** → **Run pre-flight check** again.
**Expected:** **Low** risk (≈28 %).
**Say:** "This isn't a rule of thumb. The server hid that much random data in a copy of this photo, the way the real message will be hidden, and asked our trained detector to score it. 9 KB was borderline, so it told us to stay under about 4.8 KB. Across 417 held-out test images, nothing rated Low was ever detected."

### 4. Hide (3:15 → 4:45)
**Do:** **Hide a message in this image** (or the **Hide** page with `cover.png`) → *Recipient's public key* → paste the public key → paste `message.txt` (~3.8 KB) → leave **LSB matching (±1)** and **Scattered by key** → **Hide message** → **Download**.
**Expected:** "Your message is hidden", and a PNG download.
**Say:** "The image looks identical: PSNR above 54 dB even at 50 % payload. The pixels hold no header and no signature. Without the key, the bits are indistinguishable from noise."

### 5. Reveal (4:45 → 5:45)
**Do:** **Reveal** → drop the downloaded PNG → *My private key* → drop the private key file → reveal.
**Expected:** the original message.
**Say:** "Authenticated with AES-GCM. If even one bit had changed, or the key were wrong, you'd get 'no message found', the same answer as for an image with no message at all, so the error confirms nothing."

### 6. Detect (5:45 → 7:15)
**Do:** **Detect** → drop `stego-matching.png`.
**Expected:** ≈30–45 %, *Probably no hidden data*, below the 72 % decision threshold (varies slightly per run: the keys are random).
**Do:** drop `stego-replacement.png`: the same ~8.6 KB message hidden with LSB replacement.
**Expected:** 98–100 %, *Hidden data likely*. The top features are `spa_rate_*`.
**Say:** "Same message, same photo, different embedding algorithm. Replacement is caught every time: Sample Pairs Analysis sees the pairs of pixel values it creates. Matching nudges values up or down instead, so at this size it slips under the threshold. It isn't invisible, though: our detector also compares the noise between colour channels, and catches most large matching payloads. That's why matching is the default *and* why the pre-flight check keeps messages small."

### 7. Evaluation Lab (7:15 → 9:30)

**Do:** **Lab** tab. The page has four parts, top to bottom.

1. **Live sample run** (top card, ~10 s). Leave the slider at **10 %** → **Run on 8 photos**. The cards fill in two at a time.
   **Expected:** replacement flagged on 7 of 8 photos (the peacock's texture hides it), matching on 0 of 8. Pre-flight and detector agree within a few points. PSNR is 61 dB. Matching on the *blurred leaves* sits just under the line (≈71 %), so it can flip to flagged on a given run. If it does, say so: smooth photos are the risky ones. Point at one card's changed-values map: "every dot is one colour value we changed."
   **Say:** "Eight photos the detector never trained on, hidden into live. The same payload is caught with replacement and slips through with matching."
2. **Saved results** (second card). Point at it for a moment: "these are the full held-out numbers from the report."
3. **Your own image.** Drop `cover.png` into *Run the experiments on your image* → **Run all demos** (~3–5 s):
   - **Attacks:** the control is *Recovered*. Wrong password, wrong private key, bit flips, crop and signature scan all *Failed safely*.
   - **Robustness:** PNG re-save *Recovered*. JPEG q90/q75 and resize *Failed safely*.
   - **Detector comparison** (~5 s): clean ≈23 %; replacement flagged from 10 % (≈98 %); matching passes at 5–10 % (≈28–45 %) and is flagged from 25 % (≈96 %).
   - **Quality:** PSNR 64 → 54 dB from 5 % to 50 %.
4. **Your image × sample messages** (bottom card, same image, ~7 s) → **Run 6 messages in your image**.
   **Expected:** the note, chat, email and letter pass with both algorithms (matching ≈23–28 %). The field report (12.6 KB) is flagged with replacement only (matching ≈45 %). The 40 KB dossier is flagged with both. The summary reads **60 of 60** safety checks as expected.
   Scroll to the **Long dossier** card. Point at the cyan changed pixels, the red flattest third, the yellow box, and the before/after zoom. Read the first line of *Why*.
   **Say:** "Here are our real messages in your photo. Cyan is every pixel we touched, and the yellow box is where a flat area took the most changes. Small messages blend in. The dossier fills 41 % of the image and is caught. The detector judges the whole image; the map shows where the evidence sits."

**Say:** "These are the same experiment scripts that produced the report's numbers, running live."

### 8. Close (9:30 → 10:00)
**Say:** "Three findings. The pre-flight check is a reliable guide. The embedding algorithm and the message size matter far more than the photo. And every attack we tried fails safely. Limits: LSB doesn't survive JPEG, and large payloads are detectable, even with matching. Content-adaptive embedding and JPEG-domain hiding are our future work."

---

## If something goes wrong

| Problem | Recovery (≤ 20 s) |
|---|---|
| Page won't load | Terminal: `make serve` again. If it fails a second time, switch to `fallback.mov` at the current step. |
| "Detector not available" | `models/detector.joblib` is missing or mismatched. Don't debug live; switch to the fallback video. |
| Upload rejected as too large | Use `cover.png` (512×512). Lab demos accept up to 1024×1024. |
| Reveal says "no message found" | Check the mode (*My private key* vs *Password*) and that the *downloaded* PNG was used, not `cover.png`. |
| Private key file missing, or key generation fails | Switch to the built-in example keys (~40 s, longer than the rest of this table). **Hide** → *Recipient's public key* → **Use the example key (testing only)** → hide and download again. Then **Reveal** → *My private key* → **Use the example private key**. **Say:** "This is the built-in test key pair; everyone has it, which is why the app warns that anyone could read this message." The example key only opens messages hidden with it, so you must hide again; swapping keys on Reveal alone won't work. |
| Short on time at the Keys step | Skip generating a key: on **Hide**, use **Use the example key** and carry on. Reveal then uses **Use the example private key**, so no files need handling. |
| Detector comparison is slow | It takes ~5 s; keep talking. The pre-flight and detector results above make the same point. |
| A live run (8 photos or 6 messages) is slow | Press **Stop** once half the cards are done. The finished cards and the summary already make the point. |
| Laptop fails entirely | Play `fallback.mov` from a USB stick or a phone, and narrate over it. |

## Likely questions

- **"Why not just encrypt?"** Ciphertext is visible and attracts attention. Steganography hides that a message exists at all.
- **"Can the recipient's public key find the message?"** No. It only locates a random one-time key. The message positions need the private key.
- **"Can you brute-force the password offline?"** Every guess costs a full PBKDF2 run (600,000 iterations, ≈230 ms). Nothing embedded allows a cheaper check.
- **"Does it survive WhatsApp?"** No. Recompression destroys LSBs, and the app warns about this. It fails safely: no partial or wrong message.
- **"Why a Random Forest, not a CNN?"** Scope. It's interpretable (top features per image) and fast (< 1 s per image). A CNN is future work.
- **"Was the detector tested on its own training data?"** No. The split is by source photo (720 train, 180 test), and every experiment re-checks that its covers are held out.
- **"How accurate is the detector?"** ROC-AUC 0.87 on 417 held-out images. It flags about 4 % of clean photos, and 99.5 % of what it flags really carries a message. Adding inter-channel features and 9× more photos took it from 0.73 to 0.87 and made LSB matching detectable at larger sizes.
