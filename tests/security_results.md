# StegoShield Security Test Results (format v2)

**Tests:** `tests/test_security.py`, `tests/test_crypto.py` · **Run:** `pytest tests/test_security.py tests/test_crypto.py -v`

| # | Threat | Attack | Defence | Expected result | Test |
|---|---|---|---|---|---|
| 1 | Ciphertext / tag tampering | Flip any bit of the packet (salt, nonce, length, ciphertext, tag) | AES-256-GCM tag; salt, nonce and length bound in AAD | `AuthenticationError`, no plaintext released | `test_password_mode_any_byte_tampering_fails`, `test_asymmetric_mode_tampering_fails` |
| 2 | Pixel tampering | Flip LSBs in the stego image (one slot, or half the image) | GCM tag over the whole message | `AuthenticationError` | `test_pixel_tampering_is_rejected`, `test_single_slot_tampering_is_rejected` |
| 3 | Cropping | Crop the stego image to a quarter | Slot positions depend on image size; length bounds check | `AuthenticationError`, no crash | `test_cropped_image_fails_safely` |
| 4 | Wrong key | Wrong password / unrelated private key | PBKDF2 / ECDH give different keys | `AuthenticationError` | `test_wrong_password_and_wrong_private_key` |
| 5 | **Public-key holder locates message** (v1 bug) | Use the recipient's public key to find the data and read a header | Public key only locates stage 1, which is a fresh random one-time key. The rest needs the private key | Reads different random bytes every time, no marker | `test_public_key_holder_cannot_find_message` |
| 6 | **Cheap password confirmation** (v1 bug) | Guess a password, check for a known header at cheaply derived positions | Cheap locator only reaches a random salt. Checking a guess requires PBKDF2 (600k iterations) | No marker. Each guess costs ≈230 ms instead of ≈3 ms | `test_password_guess_cannot_be_confirmed_without_pbkdf2` |
| 7 | Known-plaintext scan | Read LSBs in order, looking for a signature | No magic/version/mode embedded; length masked | `STSH` not found, even in sequential mode | `test_no_magic_bytes_in_image`, `test_packets_contain_no_magic_bytes` |
| 8 | Constant-bit fingerprint | Check the top bit of the embedded X25519 key (always 0 in raw keys) | Top bit randomised on embed, cleared on read | Both values occur | `test_asymmetric_top_bit_is_randomised` |
| 9 | Position reuse | Compare two images sent with the same password | Stage-2 positions come from the per-message salt | Positions essentially disjoint | `test_same_password_uses_different_positions` |
| 10 | Key cross-contamination | Relation between encryption key and position key | HKDF domain separation (RFC 5869) | Independent sub-keys | `test_session_subkeys_are_independent` |

## Known limitations (documented, not fixed)

- **Statistical detection:** encryption hides the content, not the act of embedding. LSB changes can still be detected statistically at high payloads. Measuring this is the job of the detector experiments (Module D).
- **X25519 key encoding:** a valid public key isn't a perfectly uniform bit string. Elligator2 would fix this and is out of scope (see `docs/payload_format.md` §4).
- **Lossy transport:** JPEG recompression or resizing destroys the message. It is rejected safely, but it can't be recovered.
