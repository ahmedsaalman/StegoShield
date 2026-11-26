---
title: StegoShield
emoji: 🛡️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
short_description: Encrypted image steganography with a detection-risk check
---

# StegoShield

StegoShield hides an AES-256-GCM encrypted message in the pixels of a PNG. Before you send the image, it estimates how likely a steganalysis detector is to notice. It can also check any image for hidden data.

**This is a demo instance for academic assessment.**

- The server is stateless. Nothing you upload is stored, logged or kept after the response.
- Passwords and private keys you enter *are* sent to this server to do the work. Use test passwords and freshly generated keys here, never real secrets.
- The Space sleeps when nobody has used it for a while. The first visit after that takes about a minute to wake it up.

Pages: Pre-flight check, Hide, Reveal, Detect, Keys, Evaluation Lab. The API docs are at `/api/docs`.
