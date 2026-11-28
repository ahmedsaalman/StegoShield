import { describe, expect, it } from "vitest";

import { describeFeature } from "./features";
import { formatBytes, formatPercent, formatProbability, parsePositiveInteger, utf8ByteLength } from "./format";

describe("parsePositiveInteger", () => {
  it.each([
    ["1", 1],
    [" 2000 ", 2000],
  ])("reads %j as %i", (text, expected) => {
    expect(parsePositiveInteger(text)).toBe(expected);
  });

  it.each(["", "0", "-3", "12.5", "1e3", "abc", "99999999999999999999"])("rejects %j", (text) => {
    expect(parsePositiveInteger(text)).toBeNull();
  });
});

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

  it("describes inter-channel colour features", () => {
    expect(describeFeature("colour_rg_h_one")).toEqual({
      label: "Channel-difference steps of ±1, left to right",
      channel: "red−green",
    });
    expect(describeFeature("colour_gb_v_cooc_31").label).toBe("Channel-difference step pair (1, -1), top to bottom");
    expect(describeFeature("colour_corr_v_br")).toEqual({
      label: "Noise correlation between channels, top to bottom",
      channel: "blue−red",
    });
  });

  it("falls back to a readable version of unknown names", () => {
    expect(describeFeature("new_feature")).toEqual({ label: "new feature", channel: null });
  });
});
