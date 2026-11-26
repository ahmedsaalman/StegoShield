import type { Choice } from "../components/ChoiceGroup";
import type { EmbeddingAlgorithm, EmbeddingLayout, KeyMethod } from "../lib/api";

export const METHOD_CHOICES: Choice<KeyMethod>[] = [
  {
    value: "password",
    label: "Password",
    description: "You and the recipient share a password.",
  },
  {
    value: "public_key",
    label: "Recipient's public key",
    description: "No shared password. Only the recipient's private key can open it.",
  },
];

export const ALGORITHM_CHOICES: Choice<EmbeddingAlgorithm>[] = [
  {
    value: "matching",
    label: "LSB matching (±1)",
    badge: "Recommended",
    description: "Nudges pixel values up or down by one. Harder for statistical tests to spot.",
  },
  {
    value: "replacement",
    label: "LSB replacement",
    description: "Overwrites the lowest bit. Classic method, easier to detect.",
  },
];

export const LAYOUT_CHOICES: Choice<EmbeddingLayout>[] = [
  {
    value: "pseudorandom",
    label: "Scattered by key",
    badge: "Recommended",
    description: "Bits go to positions only the key can compute.",
  },
  {
    value: "sequential",
    label: "Sequential",
    description: "Bits fill pixels in order. For comparison experiments only.",
  },
];
