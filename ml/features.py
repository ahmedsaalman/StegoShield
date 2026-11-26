r"""StegoShield steganalysis feature extraction.

Every feature is computed separately on the R, G and B channels, because the
message bits are embedded in each channel's least significant bit. Mixing the
channels into grayscale first would blur that signal.

Feature families (per channel):
1. LSB-Plane Statistics (bit-plane mean, variance, horizontal/vertical autocorrelation).
2. Chi-Square ($\chi^2$) Attack Statistics (PoV histogram asymmetry and p-values).
3. First-Order Difference Residuals (horizontal, vertical, diagonal gradients).
4. Spatial Co-occurrence Matrix Statistics (transitions, contrast, homogeneity, entropy).
5. Cover Image Complexity Metrics (Laplacian variance, Sobel edge energy, image entropy).
6. Sample Pairs Analysis (Dumitrescu, Wu & Wang 2003): an estimate of the LSB-replacement
   embedding rate. Unlike families 1-5 it is relative to the image itself, so it
   separates clean and stego images even when covers differ a lot.

Image-level family (computed once across channels, not per channel):
7. Inter-channel noise statistics. Camera noise in demosaiced photos is strongly
   correlated across R, G and B, so channel-difference planes (R-G, G-B, B-R) are
   smooth. Embedding changes each channel's LSBs independently, which roughens those
   planes. This is what exposes LSB matching (+/-1), which leaves no pairs-of-values
   or sample-pairs signature for families 2 and 6 to find.

Used jointly by:
- Defensive AI Detector (Module D)
- Pre-Flight Risk Scorer (Module B)
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage, stats

CHANNELS = ("r", "g", "b")

CHANNEL_FEATURE_NAMES = [
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
    # Sample Pairs Analysis
    "spa_rate",
]

COLOUR_PAIRS = ("rg", "gb", "br")
COLOUR_AXES = ("h", "v")
COLOUR_DIFF_CLIP = 2  # co-occurrences of differences clipped to [-2, 2]: 5 x 5 bins
_COLOUR_BINS = 2 * COLOUR_DIFF_CLIP + 1


def _colour_feature_names() -> list[str]:
    names = []
    for pair in COLOUR_PAIRS:
        for axis in COLOUR_AXES:
            prefix = f"colour_{pair}_{axis}"
            names += [f"{prefix}_zero", f"{prefix}_one", f"{prefix}_two"]
            names += [f"{prefix}_cooc_{i}{j}" for i in range(_COLOUR_BINS) for j in range(_COLOUR_BINS)]
    names += [f"colour_corr_{axis}_{pair}" for axis in COLOUR_AXES for pair in COLOUR_PAIRS]
    return names


COLOUR_FEATURE_NAMES = _colour_feature_names()

# Single source of truth for feature order: per-channel "<feature>_<channel>" grouped by
# channel, then the image-level inter-channel features.
FEATURE_NAMES = [f"{name}_{channel}" for channel in CHANNELS for name in CHANNEL_FEATURE_NAMES] + COLOUR_FEATURE_NAMES


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
        skew_val, kurt_val = _skew_and_kurtosis(flat, mean_val, std_val)
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


def _skew_and_kurtosis(flat: np.ndarray, mean: float, std: float) -> tuple[float, float]:
    """Population skewness and excess kurtosis (scipy.stats defaults), several times faster."""
    if std <= 1e-6:
        return 0.0, 0.0
    centred = flat - mean
    squared = centred * centred
    m2 = float(np.mean(squared))
    m3 = float(np.mean(squared * centred))
    m4 = float(np.mean(squared * squared))
    return m3 / m2**1.5, m4 / (m2 * m2) - 3.0


def extract_cooccurrence_features(gray: np.ndarray, t_bound: int = 3) -> dict[str, float]:
    """Compute spatial co-occurrence transition matrix on thresholded residuals."""
    f = gray.astype(np.float64)
    dh = np.clip(f[:, 1:] - f[:, :-1], -t_bound, t_bound)

    # Pair consecutive horizontal differences: D(x, y) and D(x, y+1)
    if dh.shape[1] >= 2:
        d1 = dh[:, :-1].reshape(-1).astype(int) + t_bound
        d2 = dh[:, 1:].reshape(-1).astype(int) + t_bound
        num_bins = 2 * t_bound + 1

        # 2D histogram transition matrix (bincount gives the same counts as histogram2d, faster)
        cooc = np.bincount(d1 * num_bins + d2, minlength=num_bins * num_bins).reshape(num_bins, num_bins)
        total = np.sum(cooc)
        p = (cooc / total) if total > 0 else np.full((num_bins, num_bins), 1.0 / (num_bins**2))
    else:
        num_bins = 2 * t_bound + 1
        p = np.full((num_bins, num_bins), 1.0 / (num_bins**2))

    # Haralick-style descriptors
    i_indices, j_indices = np.indices(p.shape)
    contrast = float(np.sum(((i_indices - j_indices) ** 2) * p))
    homogeneity = float(np.sum(p / (1.0 + np.abs(i_indices - j_indices))))
    energy = float(np.sum(p**2))
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
    """Extract all per-channel features from an image.

    Returns:
        (vector ordered as FEATURE_NAMES, dict keyed by FEATURE_NAMES)
    """
    feat_dict: dict[str, float] = {}
    planes = _channel_planes(image)
    for channel, plane in zip(CHANNELS, planes, strict=True):
        for name, value in extract_channel_features(plane).items():
            feat_dict[f"{name}_{channel}"] = value
    feat_dict.update(extract_colour_features(planes))
    vec = np.array([feat_dict[name] for name in FEATURE_NAMES], dtype=np.float64)
    return vec, feat_dict


def extract_colour_features(planes: list[np.ndarray]) -> dict[str, float]:
    """Inter-channel noise statistics (family 7) from the R, G and B planes.

    For each channel-difference plane and axis: the share of neighbouring differences
    equal to 0, 1 and 2 in magnitude, and the 5 x 5 co-occurrence of consecutive clipped
    differences. Plus the correlation of first differences between channel pairs.
    """
    red, green, blue = (plane.astype(np.int16) for plane in planes)
    difference_planes = {"rg": red - green, "gb": green - blue, "br": blue - red}
    features: dict[str, float] = {}
    for pair in COLOUR_PAIRS:
        for axis, steps in zip(COLOUR_AXES, _axis_differences(difference_planes[pair]), strict=True):
            features.update(_difference_statistics(steps, f"colour_{pair}_{axis}"))
    channels = {"r": red, "g": green, "b": blue}
    for axis, numpy_axis in zip(COLOUR_AXES, (1, 0), strict=True):
        steps = {name: np.diff(plane, axis=numpy_axis).astype(np.float64).ravel() for name, plane in channels.items()}
        for pair in COLOUR_PAIRS:
            features[f"colour_corr_{axis}_{pair}"] = _correlation(steps[pair[0]], steps[pair[1]])
    return features


def _axis_differences(plane: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Horizontal and vertical neighbour differences of a plane."""
    return plane[:, 1:] - plane[:, :-1], plane[1:, :] - plane[:-1, :]


def _difference_statistics(steps: np.ndarray, prefix: str) -> dict[str, float]:
    magnitude = np.abs(steps)
    features = {
        f"{prefix}_zero": float(np.mean(magnitude == 0)),
        f"{prefix}_one": float(np.mean(magnitude == 1)),
        f"{prefix}_two": float(np.mean(magnitude == 2)),
    }
    clipped = (np.clip(steps, -COLOUR_DIFF_CLIP, COLOUR_DIFF_CLIP) + COLOUR_DIFF_CLIP).astype(np.int32)
    index = (clipped[:, :-1] * _COLOUR_BINS + clipped[:, 1:]).ravel()
    counts = np.bincount(index, minlength=_COLOUR_BINS * _COLOUR_BINS).astype(np.float64)
    shares = counts / max(counts.sum(), 1.0)
    for flat_index, share in enumerate(shares):
        i, j = divmod(flat_index, _COLOUR_BINS)
        features[f"{prefix}_cooc_{i}{j}"] = float(share)
    return features


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    std_a, std_b = a.std(), b.std()
    if std_a == 0 or std_b == 0:
        return 0.0
    return float(np.mean((a - a.mean()) * (b - b.mean())) / (std_a * std_b))


def extract_sample_pairs_features(plane: np.ndarray) -> dict[str, float]:
    """Sample Pairs Analysis estimate of the LSB-replacement rate, over horizontal and vertical pairs.

    Solves (|W|+|Z|)/2 * p^2 + (2|X| - |P|) * p + |Y| - |X| = 0 for the smaller root p,
    where for each pair (u, v): X = v even and u < v, or v odd and u > v; Y = the
    mirror case; Z = equal values; W = values differing only in the LSB. Clean
    images give p near 0, a fully embedded image near 1.
    """
    image = plane.astype(np.int32)
    left = np.concatenate([image[:, :-1].ravel(), image[:-1, :].ravel()])
    right = np.concatenate([image[:, 1:].ravel(), image[1:, :].ravel()])
    right_is_even = right % 2 == 0
    x_count = np.sum((right_is_even & (left < right)) | (~right_is_even & (left > right)))
    y_count = np.sum((right_is_even & (left > right)) | (~right_is_even & (left < right)))
    z_count = np.sum(left == right)
    w_count = np.sum((left // 2 == right // 2) & (left != right))
    return {"spa_rate": _smaller_quadratic_root((w_count + z_count) / 2, 2 * x_count - len(left), y_count - x_count)}


def _smaller_quadratic_root(a: float, b: float, c: float) -> float:
    # A non-real root means the pair statistics show no replacement signature: report 0.
    discriminant = b * b - 4 * a * c
    if a == 0 or discriminant < 0:
        return 0.0
    return float((-b - np.sqrt(discriminant)) / (2 * a))


def extract_channel_features(plane: np.ndarray) -> dict[str, float]:
    """All CHANNEL_FEATURE_NAMES for one 2D uint8 channel."""
    features: dict[str, float] = {}
    features.update(extract_lsb_features(plane))
    features.update(extract_chi_square_features(plane))
    features.update(extract_residual_features(plane))
    features.update(extract_cooccurrence_features(plane))
    features.update(extract_complexity_features(plane))
    features.update(extract_sample_pairs_features(plane))
    return features


def channel_means(feat_dict: dict[str, float]) -> dict[str, float]:
    """Average each feature over R, G and B, keyed by CHANNEL_FEATURE_NAMES (for display and summaries)."""
    return {
        name: float(np.mean([feat_dict[f"{name}_{channel}"] for channel in CHANNELS])) for name in CHANNEL_FEATURE_NAMES
    }


def _channel_planes(image: Image.Image) -> list[np.ndarray]:
    """R, G, B planes as 2D uint8 arrays. Alpha is dropped; grayscale is used for all three."""
    if image.mode == "L":
        gray = np.array(image, dtype=np.uint8)
        return [gray, gray, gray]
    rgb = np.array(image.convert("RGB"), dtype=np.uint8)
    return [rgb[:, :, i] for i in range(3)]
