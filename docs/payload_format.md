# StegoShield Message Format (v2)

**Version:** 2 · **Code:** `core/crypto.py`, `core/embed.py`, `core/pipeline.py`

## 1. Design goals

1. **Confidentiality and integrity:** AES-256-GCM. Any changed bit is rejected.
2. **Nothing recognisable in the image:** every embedded byte is random-looking. No magic bytes, version, mode or plain length is written into pixels.
3. **Positions need the secret:** the slots holding the message can only be computed after the expensive PBKDF2 step (password mode) or the ECDH exchange (public-key mode).
4. **Uniform failure:** wrong key, no message and tampered image all give the same error, so the error can't be used to confirm that a message exists.

### Why v2 replaced v1
v1 embedded `STSH | version | mode | ...` and chose positions with a key derived from:
- the **recipient's public key** (asymmetric mode): anyone holding the public key could find the bits and read `STSH`, which proves a message exists;
- the **password via fast HKDF** (password mode): a password guess could be checked by looking for `STSH`, skipping PBKDF2 (≈3 ms per guess instead of ≈130–230 ms).

## 2. Terms

- **Slot:** one 8-bit colour value (R, G or B of a pixel; alpha is never touched). One slot carries one bit in its least significant bit (LSB).
- **Locator key:** a cheap key that only finds stage 1.
- **Session keys:** `enc_key`, `slot_key` and `mask_key`, derived with HKDF from the master secret (domain-separated by the HKDF `info` label).

## 3. What gets embedded

```
Stage 1  (at locator-key slots)
  Password mode:   salt                      16 B   random
  Public-key mode: one-time X25519 pubkey    32 B   random, top bit randomised

Stage 2  (at slot-key slots, excluding stage-1 slots)
  nonce                12 B   random
  masked length         4 B   len(ciphertext+tag) XOR mask_key
  ciphertext + tag      N B   AES-256-GCM, N = len(plaintext) + 16
```

**Overhead:** 48 B (password mode), 64 B (public-key mode).
**Capacity:** `floor(width × height × 3 / 8) − overhead` bytes of plaintext.

## 4. Key derivation

### Password mode
```
locator  = HKDF(password, salt="stegoshield-v2-locator", info="...locator-password")
master   = PBKDF2-HMAC-SHA256(password, salt, 600,000 iterations)
enc_key  = HKDF(master, info="stegoshield-v2-aes-key")
slot_key = HKDF(master, info="stegoshield-v2-slot-key")
mask_key = HKDF(master, info="stegoshield-v2-length-mask")[:4]
```
The locator is cheap, but all it reaches is the salt, which is fresh random bytes for every message. A guessed password can only be checked by running PBKDF2 and trying to decrypt.

### Public-key mode
```
locator  = HKDF(recipient_pub, salt="stegoshield-v2-locator", info="...locator-x25519")
shared   = X25519(one_time_priv, recipient_pub)
master   = HKDF(shared, salt=one_time_pub || recipient_pub, info="stegoshield-v2-x25519-master")
enc_key, slot_key, mask_key as above
```
X25519 public keys always have the top bit = 0. The sender sets it at random before embedding and the receiver clears it, so there's no constant bit. *Known limitation:* a valid X25519 key is still not a perfectly uniform 255-bit string (only about half of all values are points on the curve). Hiding that would need Elligator2 encoding, which is out of scope. With a single image this leaks at most about one bit of evidence.

## 5. Authenticated data (AAD)

These are verified by AES-GCM but never embedded:
```
AAD = "STSH" || version (0x02) || mode || stage1 || nonce || true_length (uint32 BE)
```
Changing the stage-1 bytes, nonce or length makes decryption fail. Trying to read a v2 image as another version or mode also fails.

## 6. Slot selection

`select_slots(total, count, key, exclude)` in `core/embed.py`:
1. `PCG64(SeedSequence(int(key)))` gives a stream of 64-bit values (output is stable across NumPy versions).
2. Each value `mod total` is a candidate slot. Duplicates and excluded slots are skipped.
3. The first `count` distinct survivors are the slots, in stream order.

It generates only the slots it needs, so a 12-megapixel image hides and reveals in about 1 s. It also has a **prefix property**: the first *k* slots of a request for *n ≥ k* equal a request for *k*. That lets the receiver read the 16-byte stage-2 header, learn the length, then read the rest.

**Sequential mode** (`mode="sequential"`) uses slots `0, 1, 2, …` instead. It's kept only as a baseline for the detector experiments.

## 7. Reveal procedure

1. Read 16 or 32 bytes of stage 1 from the locator slots.
2. Derive the session keys (PBKDF2, or ECDH with the private key).
3. Read 16 bytes of stage-2 header from the `slot_key` slots (excluding stage 1). Unmask the length.
4. If the length is impossible for this image, fail with the uniform error.
5. Read the full stage 2 and decrypt. A tag mismatch gives the uniform error.

## 8. Embedding algorithms

- **LSB replacement:** `p = (p & 0xFE) | bit`.
- **LSB matching (±1):** if the LSB is already right, leave it. Otherwise add or subtract 1 at random (0 → +1, 255 → −1). This avoids the pairs-of-values imbalance that the chi-square attack detects.

Both change each slot by at most 1.

## 9. Transport

The output must be saved as **PNG** (lossless). JPEG compression, resizing or cropping destroy the LSBs and the message is rejected (measured in the robustness experiment).
