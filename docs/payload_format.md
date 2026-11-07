# StegoShield Binary Payload Format Specification

**Document Version:** 1.0  
**Phase:** 0 Setup  
**Deliverable:** L03 (`docs/payload_format.md`)

---

## 1. Overview

StegoShield packages encrypted payloads into a compact, cryptographically authenticated binary structure before embedding into cover image pixels. The binary format ensures:
1. **Confidentiality:** Payloads are encrypted with AES-256-GCM.
2. **Integrity & Authenticity:** AES-GCM authentication tag verifies ciphertext authenticity. The format headers are bound as **Additional Authenticated Data (AAD)** to prevent tampering with mode flags, lengths, or nonces.
3. **Key Separation:** Encryption keys and permutation seeds are cryptographically separated using HKDF (`RFC 5869`).
4. **Indistinguishability & Defeat of Sequential Extraction:** Key-seeded pseudorandom permutations scatter bits across image channels.

---

## 2. Binary Structure

StegoShield supports two encryption modes:
- **Mode 1 (`0x01`):** Password-based symmetric encryption (PBKDF2-HMAC-SHA256).
- **Mode 2 (`0x02`):** Asymmetric public-key encryption (X25519 ECDH + HKDF).

### 2.1 Mode 1: Password-Derived Symmetric Mode (`0x01`)

```
+-----------------------------------------------------------------------------------------+
| Field                 | Size (Bytes) | Type           | Description                     |
+-----------------------------------------------------------------------------------------+
| Magic Bytes           | 4            | ASCII ("STSH") | StegoShield protocol identifier |
| Version               | 1            | uint8          | Protocol version (0x01)         |
| Mode                  | 1            | uint8          | Mode identifier (0x01)          |
| PBKDF2 Salt           | 16           | bytes          | Cryptographically random salt   |
| Nonce / IV            | 12           | bytes          | AES-GCM standard 96-bit nonce   |
| Payload Length (N)    | 4            | uint32 (BE)    | Length of Ciphertext + Auth Tag |
| Ciphertext + Tag      | N            | bytes          | AES-GCM ciphertext + 16B tag    |
+-----------------------------------------------------------------------------------------+
```

- **Header Size:** 4 + 1 + 1 + 16 + 12 + 4 = **38 bytes**
- **Total Payload Size:** $38 + N$ bytes (where $N = \text{len(plaintext)} + 16$).

### 2.2 Mode 2: Asymmetric X25519 ECDH Mode (`0x02`)

```
+-----------------------------------------------------------------------------------------+
| Field                 | Size (Bytes) | Type           | Description                     |
+-----------------------------------------------------------------------------------------+
| Magic Bytes           | 4            | ASCII ("STSH") | StegoShield protocol identifier |
| Version               | 1            | uint8          | Protocol version (0x01)         |
| Mode                  | 1            | uint8          | Mode identifier (0x02)          |
| Ephemeral Public Key  | 32           | bytes          | Raw X25519 sender public key    |
| Nonce / IV            | 12           | bytes          | AES-GCM standard 96-bit nonce   |
| Payload Length (N)    | 4            | uint32 (BE)    | Length of Ciphertext + Auth Tag |
| Ciphertext + Tag      | N            | bytes          | AES-GCM ciphertext + 16B tag    |
+-----------------------------------------------------------------------------------------+
```

- **Header Size:** 4 + 1 + 1 + 32 + 12 + 4 = **54 bytes**
- **Total Payload Size:** $54 + N$ bytes (where $N = \text{len(plaintext)} + 16$).

---

## 3. Cryptographic Key Derivation

To guarantee that the permutation generator cannot leak plaintext encryption state, keys are strictly isolated:

### 3.1 Mode 1 (Password)
1. Derive **Master Key** (32 bytes):
   $$\text{MasterKey} = \text{PBKDF2-HMAC-SHA256}(\text{password}, \text{salt}, \text{iterations}=600,000)$$
2. Sub-key Derivation via HKDF:
   - **Encryption Key:** $K_{\text{enc}} = \text{HKDF-Expand}(\text{MasterKey}, \text{info}=b"\text{stegoshield-aes-encryption}", \text{len}=32)$
   - **Permutation Seed:** $K_{\text{perm}} = \text{HKDF-Expand}(\text{MasterKey}, \text{info}=b"\text{stegoshield-pixel-permutation}", \text{len}=32)$

### 3.2 Mode 2 (Asymmetric X25519)
1. Sender generates ephemeral keypair: $(k_{\text{eph}}, K_{\text{eph}})$.
2. Compute shared secret via Diffie-Hellman:
   $$\text{SharedSecret} = \text{X25519}(k_{\text{eph}}, K_{\text{recipient}})$$
3. Derive **Master Key** (32 bytes):
   $$\text{MasterKey} = \text{HKDF-Extract}(\text{salt}=\text{None}, \text{IKM}=\text{SharedSecret})$$
4. Sub-key Derivation:
   - **Encryption Key:** $K_{\text{enc}} = \text{HKDF-Expand}(\text{MasterKey}, \text{info}=b"\text{stegoshield-aes-encryption}", \text{len}=32)$
   - **Permutation Seed:** $K_{\text{perm}} = \text{HKDF-Expand}(\text{MasterKey}, \text{info}=b"\text{stegoshield-pixel-permutation}", \text{len}=32)$

---

## 4. Additional Authenticated Data (AAD)

For both modes, the entire header preceding the ciphertext is passed as AAD to the AES-GCM cipher:
$$\text{AAD} = \text{Magic} \parallel \text{Version} \parallel \text{Mode} \parallel (\text{Salt} \text{ or } K_{\text{eph}}) \parallel \text{Nonce} \parallel \text{Length}$$

If any byte of the header is modified (e.g. tampering with the length or mode), AES-GCM verification fails and raises an `AuthenticationError`.

---

## 5. Permutation & Embedding Mapping

- Bits of the entire binary payload (Header + Ciphertext + Tag) are serialized as a bitstream:
  $$B \in \{0, 1\}^{8 \cdot \text{TotalBytes}}$$
- Total bits $L = \text{len}(B)$.
- Available image carrier capacity in bits:
  $$C = W \times H \times \text{Channels} \times \text{BitsPerChannel}$$
- Requirement: $L \le C$. If $L > C$, capacity error is raised.
- Pseudorandom Index Permutation:
  - $K_{\text{perm}}$ seeds a deterministic PRNG (`numpy.random.Generator` with `PCG64` initialized from 64-bit entropy derived from $K_{\text{perm}}$).
  - A permutation of indices $\{0, 1, \dots, C-1\}$ is generated, and the first $L$ indices dictate the embedding positions.

