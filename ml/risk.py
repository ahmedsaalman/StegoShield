"""Pre-flight cover image check (Module B): capacity and a texture-based risk estimate.

Interim version. The risk score here is a hand-tuned texture/edge/entropy
formula, labelled as such in its output. Phase 4 replaces it with the
detector-in-the-loop check (embed a test payload, ask the trained detector).
The separate risk regressor from the original proposal is out of scope and
has been removed.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from core.capacity import calculate_image_capacity, compute_payload_ratio
from ml.features import channel_means, extract_features


class PreFlightRiskScorer:
    """Evaluates cover image detectability risk before steganographic embedding."""

    def _heuristic_risk(self, feat_dict: dict[str, float], payload_ratio: float) -> float:
        """Multi-factor texture complexity & capacity model.

        Natural images with high edge density and variance absorb LSB changes smoothly.
        Smooth, flat images (e.g. clear sky, synthetic gradients) exhibit high detectability.
        """
        # 1. Texture penalty based on Laplacian variance (lower variance -> higher risk)
        lap_var = feat_dict.get("img_laplacian_var", 100.0)
        # Logarithmic normalization: lap_var < 50 is very smooth, > 1000 is heavily textured
        lap_norm = np.clip(np.log10(max(1.0, lap_var)) / 3.5, 0.0, 1.0)
        texture_risk = 1.0 - lap_norm

        # 2. Edge energy penalty (lower edge energy -> higher risk)
        edge_energy = feat_dict.get("img_sobel_edge_energy", 10.0)
        edge_norm = np.clip(edge_energy / 40.0, 0.0, 1.0)
        edge_risk = 1.0 - edge_norm

        # 3. Histogram entropy penalty (lower entropy -> less information richness)
        hist_ent = feat_dict.get("img_histogram_entropy", 6.0)
        entropy_norm = np.clip(hist_ent / 8.0, 0.0, 1.0)
        entropy_risk = 1.0 - entropy_norm

        # Base carrier detectability vulnerability (independent of payload)
        base_vulnerability = 0.45 * texture_risk + 0.35 * edge_risk + 0.20 * entropy_risk

        # 4. Payload scaling: Higher payload ratios dramatically increase detectability
        # If payload_ratio is zero (pre-embedding audit), default to typical 10% payload assumption
        effective_ratio = payload_ratio if payload_ratio > 0 else 0.10
        ratio_multiplier = np.clip(effective_ratio / 0.25, 0.1, 2.0)

        raw_score = base_vulnerability * (0.6 + 0.6 * ratio_multiplier)
        return float(np.clip(raw_score, 0.05, 0.95))

    def evaluate(
        self,
        image: Image.Image,
        target_payload_bytes: int = 0,
    ) -> dict[str, Any]:
        """Perform comprehensive pre-flight cover image risk audit.

        Args:
            image: Candidate carrier PIL image.
            target_payload_bytes: Planned payload size in bytes (0 for general audit).

        Returns:
            dict: Risk metrics, Low/Medium/High classification, gauge color, and recommendations.
        """
        capacity = calculate_image_capacity(image)
        total_slots = capacity["total_carrier_bits"]
        payload_ratio = compute_payload_ratio(target_payload_bytes, total_slots) if target_payload_bytes > 0 else 0.0

        _, channel_feats = extract_features(image)
        feat_dict = channel_means(channel_feats)  # heuristics read channel-averaged values

        risk_score = self._heuristic_risk(feat_dict, payload_ratio)

        # Categorize into Low / Medium / High
        if risk_score < 0.35:
            risk_level = "Low"
            risk_color = "#28a745"  # Green
            risk_badge = "🟢 Low Detectability Risk"
            recommendation = (
                "Excellent carrier image! The high texture and edge density provide "
                "superior steganographic masking against AI detectors."
            )
        elif risk_score <= 0.65:
            risk_level = "Medium"
            risk_color = "#fd7e14"  # Orange
            risk_badge = "🟠 Moderate Detectability Risk"
            recommendation = (
                "Acceptable carrier image. Keep your payload under the recommended "
                f"safe limit ({capacity['safe_payload_bytes']:,} bytes) to maintain stealth."
            )
        else:
            risk_level = "High"
            risk_color = "#dc3545"  # Red
            risk_badge = "🔴 High Detectability Risk"
            recommendation = (
                "Carrier image is smooth, low-variance, or flat (e.g. plain sky/gradient). "
                "Micro-pixel modifications will be statistically prominent. "
                "Recommend choosing an image with richer texture, foliage, or complex edges."
            )

        # Texture classification
        lap_var = feat_dict.get("img_laplacian_var", 0.0)
        if lap_var > 300:
            texture_desc = "Highly Textured (Dense detail)"
        elif lap_var > 80:
            texture_desc = "Moderately Textured (Standard photos)"
        else:
            texture_desc = "Smooth / Low Variance (High risk)"

        return {
            "risk_score": risk_score,
            "risk_score_percent": f"{risk_score * 100:.1f}%",
            "risk_level": risk_level,
            "risk_color": risk_color,
            "risk_badge": risk_badge,
            "texture_description": texture_desc,
            "recommendation": recommendation,
            "capacity": capacity,
            "target_payload_bytes": target_payload_bytes,
            "payload_ratio_percent": f"{payload_ratio * 100:.2f}%" if target_payload_bytes > 0 else "N/A",
            "model_type": "Texture heuristic (interim, replaced by detector-in-the-loop in Phase 4)",
            "features": {
                "laplacian_variance": f"{feat_dict.get('img_laplacian_var', 0):.1f}",
                "edge_energy": f"{feat_dict.get('img_sobel_edge_energy', 0):.2f}",
                "histogram_entropy": f"{feat_dict.get('img_histogram_entropy', 0):.2f}",
                "lsb_mean": f"{feat_dict.get('lsb_mean', 0):.3f}",
            },
        }
