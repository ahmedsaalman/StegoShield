r"""StegoShield Steganalysis Feature Extraction Engine (Task L16).

Extracts rich statistical features from cover and stego images:
1. LSB-Plane Statistics (bit-plane mean, variance, horizontal/vertical autocorrelation).
2. Chi-Square ($\chi^2$) Attack Statistics (PoV histogram asymmetry and p-values).
3. First-Order Difference Residuals (horizontal, vertical, diagonal gradients).
4. Spatial Co-occurrence Matrix Statistics (transitions, contrast, homogeneity, entropy).
5. Cover Image Complexity Metrics (Laplacian variance, Sobel edge energy, image entropy).

Used jointly by:
- Defensive AI Detector (Module D)
- Pre-Flight Risk Scorer (Module B)
"""

from __future__ import annotations

from typing import Dict, Any, Tuple
from PIL import Image
import numpy as np
from scipy import stats, ndimage


FEATURE_NAMES = [
    # LSB Bit-Plane Statistics
    "lsb_mean",
    "lsb_variance",
    "lsb_horiz_transition_rate",
    "lsb_vert_transition_rate",
    "lsb_entropy",
    # Chi-Square Attack Statistics
    "chi_square_stat",
    "chi_square_norm",
    "chi_square_p_value",
    # Difference Residual Statistics
    "diff_h_mean",
    "diff_h_std",
    "diff_h_skew",
    "diff_h_kurtosis",
    "diff_v_mean",
    "diff_v_std",
    "diff_v_skew",
    "diff_v_kurtosis",
    "diff_d_mean",
    "diff_d_std",
    # Spatial Co-occurrence (Thresholded Residuals)
    "cooc_contrast",
    "cooc_homogeneity",
    "cooc_energy",
    "cooc_entropy",
    # Pre-Flight Cover Complexity Metrics
    "img_intensity_mean",
    "img_intensity_std",
    "img_laplacian_var",
    "img_sobel_edge_energy",
    "img_histogram_entropy",
]


def _to_grayscale_array(image: Image.Image) -> np.ndarray:
    """Convert PIL image to 2D uint8 numpy array."""
    if image.mode != "L":
        gray = image.convert("L")
    else:
        gray = image
    return np.array(gray, dtype=np.uint8)


def extract_lsb_features(gray: np.ndarray) -> dict[str, float]:
    """Extract statistics from the least significant bit plane."""
    lsb = (gray & 1).astype(np.float64)
    lsb_mean = float(np.mean(lsb))
    lsb_var = float(np.var(lsb))

    # Horizontal adjacent bit transition rate P(LSB(x) != LSB(x+1))
    h_transitions = np.abs(lsb[:, 1:] - lsb[:, :-1])
    h_rate = float(np.mean(h_transitions)) if h_transitions.size > 0 else 0.5

    # Vertical adjacent bit transition rate P(LSB(y) != LSB(y+1))
    v_transitions = np.abs(lsb[1:, :] - lsb[:-1, :])
    v_rate = float(np.mean(v_transitions)) if v_transitions.size > 0 else 0.5

    # LSB Shannon entropy
    p1 = np.clip(lsb_mean, 1e-9, 1.0 - 1e-9)
    p0 = 1.0 - p1
    lsb_ent = float(-(p0 * np.log2(p0) + p1 * np.log2(p1)))

    return {
        "lsb_mean": lsb_mean,
        "lsb_variance": lsb_var,
        "lsb_horiz_transition_rate": h_rate,
        "lsb_vert_transition_rate": v_rate,
        "lsb_entropy": lsb_ent,
    }


def extract_chi_square_features(gray: np.ndarray) -> dict[str, float]:
    """Perform Westfeld-Pfitzmann Chi-Square test on Pairs of Values (PoVs)."""
    flat = gray.reshape(-1)
    hist, _ = np.histogram(flat, bins=256, range=(0, 256))

    # Pair bins: (2k, 2k+1) for k in 0..127
    evens = hist[0::2].astype(np.float64)
    odds = hist[1::2].astype(np.float64)
    expected = (evens + odds) / 2.0

    valid_mask = expected > 0
    k_valid = int(np.sum(valid_mask))

    if k_valid > 1:
        chi_stat = float(np.sum(((evens[valid_mask] - expected[valid_mask]) ** 2) / expected[valid_mask]))
        dof = max(1, k_valid - 1)
        chi_norm = chi_stat / dof
        # Survival function (1 - CDF)
        p_val = float(stats.chi2.sf(chi_stat, dof))
    else:
        chi_stat = 0.0
        chi_norm = 0.0
        p_val = 1.0

    return {
        "chi_square_stat": chi_stat,
        "chi_square_norm": chi_norm,
        "chi_square_p_value": p_val,
    }


def extract_residual_features(gray: np.ndarray) -> dict[str, float]:
    """Extract first-order directional pixel difference statistics."""
    f = gray.astype(np.float64)

    # Horizontal, vertical, diagonal differences
    dh = f[:, 1:] - f[:, :-1]
    dv = f[1:, :] - f[:-1, :]
    dd = f[1:, 1:] - f[:-1, :-1]

    def _stats(arr: np.ndarray, prefix: str) -> dict[str, float]:
        flat = arr.reshape(-1)
        mean_val = float(np.mean(flat))
        std_val = float(np.std(flat))
        skew_val = float(stats.skew(flat)) if std_val > 1e-6 else 0.0
        kurt_val = float(stats.kurtosis(flat)) if std_val > 1e-6 else 0.0
        return {
            f"{prefix}_mean": mean_val,
            f"{prefix}_std": std_val,
            f"{prefix}_skew": skew_val,
            f"{prefix}_kurtosis": kurt_val,
        }

    res_h = _stats(dh, "diff_h")
    res_v = _stats(dv, "diff_v")
    res_d = {
        "diff_d_mean": float(np.mean(dd)),
        "diff_d_std": float(np.std(dd)),
    }

    out = {}
    out.update(res_h)
    out.update(res_v)
    out.update(res_d)
    return out


def extract_cooccurrence_features(gray: np.ndarray, t_bound: int = 3) -> dict[str, float]:
    """Compute spatial co-occurrence transition matrix on thresholded residuals."""
    f = gray.astype(np.float64)
    dh = np.clip(f[:, 1:] - f[:, :-1], -t_bound, t_bound)

    # Pair consecutive horizontal differences: D(x, y) and D(x, y+1)
    if dh.shape[1] >= 2:
        d1 = dh[:, :-1].reshape(-1).astype(int) + t_bound
        d2 = dh[:, 1:].reshape(-1).astype(int) + t_bound
        num_bins = 2 * t_bound + 1

        # 2D histogram transition matrix
        cooc, _, _ = np.histogram2d(d1, d2, bins=num_bins, range=[[0, num_bins], [0, num_bins]])
        total = np.sum(cooc)
        p = (cooc / total) if total > 0 else np.full((num_bins, num_bins), 1.0 / (num_bins ** 2))
    else:
        num_bins = 2 * t_bound + 1
        p = np.full((num_bins, num_bins), 1.0 / (num_bins ** 2))

    # Haralick-style descriptors
    i_indices, j_indices = np.indices(p.shape)
    contrast = float(np.sum(((i_indices - j_indices) ** 2) * p))
    homogeneity = float(np.sum(p / (1.0 + np.abs(i_indices - j_indices))))
    energy = float(np.sum(p ** 2))
    entropy_val = float(-np.sum(p * np.log2(np.clip(p, 1e-12, 1.0))))

    return {
        "cooc_contrast": contrast,
        "cooc_homogeneity": homogeneity,
        "cooc_energy": energy,
        "cooc_entropy": entropy_val,
    }


def extract_complexity_features(gray: np.ndarray) -> dict[str, float]:
    """Compute cover texture and edge complexity metrics for pre-flight risk evaluation."""
    f = gray.astype(np.float64)
    mean_val = float(np.mean(f))
    std_val = float(np.std(f))

    # Laplacian variance (texture / focus / high-frequency variation)
    laplacian_kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
    lap = ndimage.convolve(f, laplacian_kernel, mode="reflect")
    lap_var = float(np.var(lap))

    # Sobel edge energy
    sobel_h = ndimage.sobel(f, axis=1)
    sobel_v = ndimage.sobel(f, axis=0)
    sobel_mag = np.hypot(sobel_h, sobel_v)
    edge_energy = float(np.mean(sobel_mag))

    # Intensity histogram entropy
    hist, _ = np.histogram(f.reshape(-1), bins=256, range=(0, 256), density=True)
    hist = hist[hist > 0]
    hist_entropy = float(-np.sum(hist * np.log2(hist))) if hist.size > 0 else 0.0

    return {
        "img_intensity_mean": mean_val,
        "img_intensity_std": std_val,
        "img_laplacian_var": lap_var,
        "img_sobel_edge_energy": edge_energy,
        "img_histogram_entropy": hist_entropy,
    }


def extract_features(image: Image.Image) -> tuple[np.ndarray, dict[str, float]]:
    """Extract all 27 steganalysis and risk features from an image.
    
    Returns:
        tuple[np.ndarray, dict[str, float]]: (feature_vector_1d, feature_dict)
    """
    gray = _to_grayscale_array(image)

    feat_dict: dict[str, float] = {}
    feat_dict.update(extract_lsb_features(gray))
    feat_dict.update(extract_chi_square_features(gray))
    feat_dict.update(extract_residual_features(gray))
    feat_dict.update(extract_cooccurrence_features(gray))
    feat_dict.update(extract_complexity_features(gray))

    # Build ordered vector
    vec = np.array([feat_dict[k] for k in FEATURE_NAMES], dtype=np.float64)
    return vec, feat_dict

