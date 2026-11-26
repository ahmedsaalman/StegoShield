"""Transport robustness: does a hidden message survive re-saving, JPEG and resizing?

Hides a real format-v2 message (both key modes, LSB matching), passes the stego
image through each transport, and tries to reveal it. Each trial ends in one of:

- recovered:      the exact message came back
- failed_safely:  AuthenticationError / InvalidPayloadError, no output
- unsafe:         wrong output or an unexpected crash (a bug if it ever happens)

Expected: PNG re-save recovers; JPEG and resizing fail safely, because LSBs do
not survive lossy compression or resampling. Message content is seeded; keys and
salts come from os.urandom as in production, so outcomes (not bytes) are what reruns reproduce.

Usage:
    python -m experiments.robustness
    python -m experiments.robustness --covers 20
"""

from __future__ import annotations

import io
from concurrent.futures import ProcessPoolExecutor
from enum import StrEnum
from functools import partial
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from PIL import Image

from core.crypto import StegoCryptoError
from core.keys import generate_keypair
from core.pipeline import (
    stego_decode_asymmetric,
    stego_decode_password,
    stego_encode_asymmetric,
    stego_encode_password,
)
from experiments.common import (
    BAR_HATCHES,
    assert_held_out,
    base_argument_parser,
    held_out_cover_ids,
    load_cover,
    save_figure,
    seeded_bytes,
    seeded_key,
    write_results,
)

DEFAULT_ROBUSTNESS_COVERS = 20
MESSAGE_BYTES = 1024
ALGORITHM = "matching"  # the web app's default
KEY_MODES = ("password", "asymmetric")
PASSWORD_LENGTH_BYTES = 12
RESIZE_FACTOR = 0.5


class Transport(StrEnum):
    """What happens to the stego image between sender and recipient."""

    PNG_RESAVE = "png_resave"
    JPEG_Q90 = "jpeg_q90"
    JPEG_Q75 = "jpeg_q75"
    RESIZE_50 = "resize_50"


class Outcome(StrEnum):
    """Result of trying to reveal the message after transport."""

    RECOVERED = "recovered"
    FAILED_SAFELY = "failed_safely"
    UNSAFE = "unsafe"


TRANSPORT_LABELS = {
    Transport.PNG_RESAVE: "PNG re-save",
    Transport.JPEG_Q90: "JPEG q90",
    Transport.JPEG_Q75: "JPEG q75",
    Transport.RESIZE_50: "Resize 50 %",
}
JPEG_QUALITY = {Transport.JPEG_Q90: 90, Transport.JPEG_Q75: 75}


def main() -> None:
    """Command-line entry point."""
    parser = base_argument_parser("Extraction success after PNG re-save, JPEG and resizing.")
    parser.set_defaults(covers=DEFAULT_ROBUSTNESS_COVERS)
    args = parser.parse_args()
    cover_ids = held_out_cover_ids(limit=args.covers)
    assert_held_out(cover_ids)
    print(f"[*] robustness: {len(cover_ids)} held-out covers x {len(KEY_MODES)} modes x {len(Transport)} transports")
    trials = run_robustness(cover_ids, seed=args.seed, cover_dir=args.cover_dir, workers=args.workers)
    summary = summarise_robustness(trials)
    print(summary.to_string(index=False))
    print(f"[+] {write_results(trials, 'robustness')}, {write_results(summary, 'robustness_summary')}")
    print(f"[+] {save_figure(plot_robustness(summary), 'robustness')}")


def apply_transport(image: Image.Image, transport: Transport) -> Image.Image:
    """Simulate sending the image: re-encode it (PNG or JPEG) or resize it."""
    if transport is Transport.RESIZE_50:
        size = (round(image.width * RESIZE_FACTOR), round(image.height * RESIZE_FACTOR))
        return image.resize(size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    if transport is Transport.PNG_RESAVE:
        image.save(buffer, format="PNG")
    else:
        image.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY[transport])
    buffer.seek(0)
    with Image.open(buffer) as received:
        return received.convert(image.mode)


def transport_trial(cover: Image.Image, message: bytes, password: str, transport: Transport, key_mode: str) -> Outcome:
    """Hide `message`, send the image through `transport`, try to reveal it."""
    if key_mode == "password":
        stego = stego_encode_password(cover, message, password, algorithm=ALGORITHM)
        reveal = partial(stego_decode_password, password=password)
    else:
        private_key, public_key = generate_keypair()
        stego = stego_encode_asymmetric(cover, message, public_key, algorithm=ALGORITHM)
        reveal = partial(stego_decode_asymmetric, recipient_private_key=private_key)
    return _reveal_outcome(reveal, apply_transport(stego, transport), message)


def run_robustness(cover_ids: list[str], seed: int, cover_dir: Path, workers: int = 1) -> pd.DataFrame:
    """One row per cover x key mode x transport."""
    rows_for = partial(_cover_rows, seed=seed, cover_dir=cover_dir)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            per_cover = list(pool.map(rows_for, cover_ids))
    else:
        per_cover = [rows_for(cover_id) for cover_id in cover_ids]
    return pd.DataFrame([row for rows in per_cover for row in rows])


def summarise_robustness(trials: pd.DataFrame) -> pd.DataFrame:
    """Share of trials per outcome for each transport (both key modes pooled)."""
    counts = pd.crosstab(trials["transport"], trials["outcome"]).reindex(
        index=[t.value for t in Transport], columns=[o.value for o in Outcome], fill_value=0
    )
    summary = counts.assign(n_trials=counts.sum(axis=1))
    for outcome in Outcome:
        summary[f"{outcome.value}_rate"] = summary[outcome.value] / summary["n_trials"]
    return summary.reset_index().assign(seed=trials["seed"].iloc[0])


def plot_robustness(summary: pd.DataFrame) -> Figure:
    """Stacked bars: share of trials recovered / failed safely / unsafe per transport."""
    figure, axis = plt.subplots(figsize=(6.5, 3.6))
    labels = [TRANSPORT_LABELS[Transport(value)] for value in summary["transport"]]
    bottom = np.zeros(len(summary))
    shades = ("0.2", "0.75", "white")
    for outcome, shade, hatch in zip(Outcome, shades, BAR_HATCHES, strict=False):
        rates = summary[f"{outcome.value}_rate"].to_numpy() * 100
        axis.bar(
            labels, rates, bottom=bottom, color=shade, edgecolor="black", hatch=hatch, label=_outcome_label(outcome)
        )
        bottom += rates
    axis.set(ylabel="Share of trials (%)", ylim=(0, 100), title="Message extraction after transport")
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    figure.tight_layout()
    return figure


def _reveal_outcome(reveal, received: Image.Image, message: bytes) -> Outcome:
    try:
        revealed = reveal(received)
    except StegoCryptoError:
        return Outcome.FAILED_SAFELY
    except Exception:  # noqa: BLE001 - measuring: any other crash is a finding, not a reason to stop
        return Outcome.UNSAFE
    return Outcome.RECOVERED if revealed == message else Outcome.UNSAFE


def _cover_rows(cover_id: str, seed: int, cover_dir: Path) -> list[dict]:
    cover = load_cover(cover_id, cover_dir)
    message = seeded_bytes(seeded_key(seed, "robustness-message", cover_id), MESSAGE_BYTES)
    password = seeded_bytes(seeded_key(seed, "robustness-password", cover_id), PASSWORD_LENGTH_BYTES).hex()
    return [
        {
            "cover_id": cover_id,
            "key_mode": key_mode,
            "transport": transport.value,
            "outcome": transport_trial(cover, message, password, transport, key_mode).value,
            "message_bytes": MESSAGE_BYTES,
            "algorithm": ALGORITHM,
            "seed": seed,
        }
        for key_mode, transport in product(KEY_MODES, Transport)
    ]


def _outcome_label(outcome: Outcome) -> str:
    return {"recovered": "Recovered", "failed_safely": "Failed safely", "unsafe": "Unsafe"}[outcome.value]


if __name__ == "__main__":
    main()
