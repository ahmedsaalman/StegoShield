import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RISK_PRESENTATION } from "../lib/presentation";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("states the status in words and numbers, not only colour", () => {
    render(<StatusBadge status={RISK_PRESENTATION.high} value="81%" />);

    expect(screen.getByText("High risk")).toBeInTheDocument();
    expect(screen.getByText("81%")).toBeInTheDocument();
  });

  it("hides the decorative icon from assistive technology", () => {
    const { container } = render(<StatusBadge status={RISK_PRESENTATION.low} />);

    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
