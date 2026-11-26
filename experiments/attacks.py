"""Attack demos: tamper with a real stego image or use the wrong key, and check nothing leaks.

The Evaluation Lab runs these live on an uploaded image. The exhaustive versions
are the tests in tests/test_security.py (run by experiments/security.py).

Outcomes reuse experiments.robustness.Outcome:
- recovered:      only for the control (right key, untouched image)
- failed_safely:  the attack got nothing (AuthenticationError / InvalidPayloadError, or no marker found)
- unsafe:         the attack succeeded or the code crashed (a bug if it ever happens)

Usage:
    python -m experiments.attacks --covers 5
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import partial

import numpy as np
import pandas as pd
from PIL import Image

from core.crypto import MAGIC
from core.embed import bits_to_bytes, image_to_carrier
from core.keys import generate_keypair
from core.pipeline import (
    stego_decode_asymmetric,
    stego_decode_password,
    stego_encode_asymmetric,
    stego_encode_password,
)
from experiments.common import (
    assert_held_out,
    base_argument_parser,
    held_out_cover_ids,
    load_cover,
    seeded_bytes,
    seeded_key,
    write_results,
)
from experiments.robustness import ALGORITHM, Outcome, reveal_outcome

MESSAGE_BYTES = 256
FLIPPED_SLOT_SHARE = 0.5
CROP_KEEP_SHARE = 0.75


class Attack(StrEnum):
    """One way an attacker (or an accident) can go after a hidden message."""

    CONTROL = "control"
    WRONG_PASSWORD = "wrong_password"
    WRONG_PRIVATE_KEY = "wrong_private_key"
    FLIP_LSBS = "flip_lsbs"
    CROP = "crop"
    SIGNATURE_SCAN = "signature_scan"


ATTACK_DESCRIPTIONS = {
    Attack.CONTROL: "Right key, untouched image: the message should come back.",
    Attack.WRONG_PASSWORD: "Reveal a password-protected message with a different password.",
    Attack.WRONG_PRIVATE_KEY: "Reveal a public-key message with someone else's private key.",
    Attack.FLIP_LSBS: "Flip the lowest bit of half the colour values, then reveal with the right key.",
    Attack.CROP: "Crop the image to its central 75 %, then reveal with the right key.",
    Attack.SIGNATURE_SCAN: "Read every lowest bit in order and search for the StegoShield signature.",
}


@dataclass(frozen=True)
class AttackResult:
    """What one attack achieved."""

    attack: Attack
    outcome: Outcome


def main() -> None:
    """Command-line entry point."""
    parser = base_argument_parser("Run every attack demo on held-out covers.")
    parser.set_defaults(covers=5)
    args = parser.parse_args()
    cover_ids = held_out_cover_ids(limit=args.covers)
    assert_held_out(cover_ids)
    rows = [
        {"cover_id": cover_id, "attack": result.attack.value, "outcome": result.outcome.value, "seed": args.seed}
        for cover_id in cover_ids
        for result in run_all_attacks(load_cover(cover_id, args.cover_dir), args.seed, label=cover_id)
    ]
    results = pd.DataFrame(rows)
    print(pd.crosstab(results["attack"], results["outcome"]).to_string())
    print(f"[+] {write_results(results, 'attacks')}")


def run_all_attacks(cover: Image.Image, seed: int, label: str) -> list[AttackResult]:
    """Every attack in `Attack` order against fresh stego images made from `cover`."""
    message = seeded_bytes(seeded_key(seed, "attack-message", label), MESSAGE_BYTES)
    return [AttackResult(attack, run_attack(cover, attack, message, seed)) for attack in Attack]


def run_attack(cover: Image.Image, attack: Attack, message: bytes, seed: int) -> Outcome:
    """Hide `message` in `cover`, carry out `attack`, and report what the attacker got."""
    if attack is Attack.WRONG_PASSWORD:
        stego = stego_encode_password(cover, message, "correct horse battery staple", algorithm=ALGORITHM)
        return reveal_outcome(partial(stego_decode_password, password="Tr0ub4dor&3"), stego, message)

    private_key, public_key = generate_keypair()
    stego = stego_encode_asymmetric(cover, message, public_key, algorithm=ALGORITHM)
    if attack is Attack.SIGNATURE_SCAN:
        return Outcome.UNSAFE if MAGIC in sequential_lsb_bytes(stego) else Outcome.FAILED_SAFELY
    if attack is Attack.WRONG_PRIVATE_KEY:
        private_key, _ = generate_keypair()
    reveal = partial(stego_decode_asymmetric, recipient_private_key=private_key)
    return reveal_outcome(reveal, _tamper(stego, attack, seed), message)


def sequential_lsb_bytes(image: Image.Image) -> bytes:
    """Every lowest bit of the image, in pixel order, packed into bytes."""
    _, flat, _ = image_to_carrier(image)
    return bits_to_bytes(flat & 1)


def _tamper(stego: Image.Image, attack: Attack, seed: int) -> Image.Image:
    if attack is Attack.FLIP_LSBS:
        pixels = np.asarray(stego.convert("RGB")).copy()
        flip = np.random.default_rng(seed).random(pixels.shape) < FLIPPED_SLOT_SHARE
        return Image.fromarray(pixels ^ flip.astype(np.uint8))
    if attack is Attack.CROP:
        margin_x = round(stego.width * (1 - CROP_KEEP_SHARE) / 2)
        margin_y = round(stego.height * (1 - CROP_KEEP_SHARE) / 2)
        return stego.crop((margin_x, margin_y, stego.width - margin_x, stego.height - margin_y))
    return stego


if __name__ == "__main__":
    main()
