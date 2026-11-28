import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScrollIntoView } from "./ScrollIntoView";

function stubReducedMotion(isReduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: isReduced && query.includes("reduce") }));
}

/** jsdom doesn't implement scrolling, so the method is added for the test and removed again after it. */
function stubScrollIntoView() {
  const scroll = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { value: scroll, configurable: true });
  return scroll;
}

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
});

describe("ScrollIntoView", () => {
  it("scrolls its content into view smoothly when it appears", () => {
    stubReducedMotion(false);
    const scroll = stubScrollIntoView();

    render(<ScrollIntoView>Result</ScrollIntoView>);

    expect(scroll).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });

  it("jumps without animation when the user prefers less motion", () => {
    stubReducedMotion(true);
    const scroll = stubScrollIntoView();

    render(<ScrollIntoView>Result</ScrollIntoView>);

    expect(scroll).toHaveBeenCalledWith({ behavior: "auto", block: "start" });
  });
});
