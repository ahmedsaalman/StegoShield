// Human-readable names for the detector's statistical features (ml/features.py).

const CHANNELS: Record<string, string> = { r: "red", g: "green", b: "blue" };

const FEATURE_LABELS: Record<string, string> = {
  lsb_mean: "Share of 1s in the lowest bits",
  lsb_variance: "Lowest-bit variance",
  lsb_horiz_transition_rate: "Lowest-bit changes, left to right",
  lsb_vert_transition_rate: "Lowest-bit changes, top to bottom",
  lsb_entropy: "Lowest-bit randomness",
  chi_square_stat: "Pixel-pair imbalance (chi-square)",
  chi_square_norm: "Pixel-pair imbalance, normalised",
  chi_square_p_value: "Pixel-pair test p-value",
  diff_h_mean: "Horizontal neighbour difference, mean",
  diff_h_std: "Horizontal neighbour difference, spread",
  diff_h_skew: "Horizontal neighbour difference, skew",
  diff_h_kurtosis: "Horizontal neighbour difference, peakedness",
  diff_v_mean: "Vertical neighbour difference, mean",
  diff_v_std: "Vertical neighbour difference, spread",
  diff_v_skew: "Vertical neighbour difference, skew",
  diff_v_kurtosis: "Vertical neighbour difference, peakedness",
  diff_d_mean: "Diagonal neighbour difference, mean",
  diff_d_std: "Diagonal neighbour difference, spread",
  cooc_contrast: "Neighbour co-occurrence contrast",
  cooc_homogeneity: "Neighbour co-occurrence homogeneity",
  cooc_energy: "Neighbour co-occurrence energy",
  cooc_entropy: "Neighbour co-occurrence entropy",
  img_intensity_mean: "Average brightness",
  img_intensity_std: "Brightness spread",
  img_laplacian_var: "Fine texture (Laplacian variance)",
  img_sobel_edge_energy: "Edge strength",
  img_histogram_entropy: "Colour-level variety",
};

export interface FeatureDescription {
  label: string;
  channel: string | null;
}

export function describeFeature(featureName: string): FeatureDescription {
  const match = /^(.*)_([rgb])$/.exec(featureName);
  const baseName = match?.[1] ?? featureName;
  const channelCode = match?.[2];
  return {
    label: FEATURE_LABELS[baseName] ?? baseName.replaceAll("_", " "),
    channel: channelCode ? (CHANNELS[channelCode] ?? null) : null,
  };
}
