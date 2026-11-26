import { describe, expect, it } from "vitest";

import { describeFeature } from "./features";
import { formatBytes, formatPercent, formatProbability, utf8ByteLength } from "./format";

describe("formatBytes", () => {
  it.each([
    [1, "1 byte"],
    [500, "500 bytes"],
    [1536, "1.5 KB"],
    [3 * 1024 * 1024, "3 MB"],
  ])("formats %i as %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });
});

describe("formatProbability", () => {
  it("rounds a probability to a whole percentage", () => {
    expect(formatProbability(0.634)).toBe("63%");
  });
});

describe("formatPercent", () => {
  it("keeps one decimal for values below one percent", () => {
    expect(formatPercent(0.42)).toBe("0.4%");
  });

  it("rounds larger values", () => {
    expect(formatPercent(12.6)).toBe("13%");
  });
});

describe("utf8ByteLength", () => {
  it("counts multi-byte characters by their encoded size", () => {
    expect(utf8ByteLength("a☀")).toBe(4);
  });
});

describe("describeFeature", () => {
  it("turns a per-channel feature name into words", () => {
    expect(describeFeature("lsb_horiz_transition_rate_g")).toEqual({
      label: "Lowest-bit changes, left to right",
      channel: "green",
    });
  });

  it("falls back to a readable version of unknown names", () => {
    expect(describeFeature("new_feature")).toEqual({ label: "new feature", channel: null });
  });
});
