import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { centredScrollLeft, scrollEdges, TabBar } from "./TabBar";

const TABS = [
  { to: "/", label: "Overview", end: true },
  { to: "/keys", label: "Keys" },
  { to: "/lab", label: "Lab" },
];

/** jsdom has no layout, so give the nav the sizes a 390 px phone would. */
function setScrollBox(element: HTMLElement, box: { scrollLeft: number; scrollWidth: number; clientWidth: number }) {
  Object.defineProperty(element, "scrollWidth", { configurable: true, value: box.scrollWidth });
  Object.defineProperty(element, "clientWidth", { configurable: true, value: box.clientWidth });
  element.scrollLeft = box.scrollLeft;
}

describe("scrollEdges", () => {
  it("reports hidden content on either side", () => {
    expect(scrollEdges({ scrollLeft: 0, scrollWidth: 500, clientWidth: 390 })).toEqual({
      hasMoreBefore: false,
      hasMoreAfter: true,
    });
    expect(scrollEdges({ scrollLeft: 50, scrollWidth: 500, clientWidth: 390 })).toEqual({
      hasMoreBefore: true,
      hasMoreAfter: true,
    });
    expect(scrollEdges({ scrollLeft: 110, scrollWidth: 500, clientWidth: 390 })).toEqual({
      hasMoreBefore: true,
      hasMoreAfter: false,
    });
  });

  it("shows no fades when everything fits, ignoring sub-pixel scroll", () => {
    expect(scrollEdges({ scrollLeft: 1, scrollWidth: 900, clientWidth: 900 })).toEqual({
      hasMoreBefore: false,
      hasMoreAfter: false,
    });
  });
});

describe("centredScrollLeft", () => {
  const nav = { clientWidth: 390, scrollWidth: 520 };

  it("centres a tab in the middle of the bar", () => {
    expect(centredScrollLeft(nav, { offsetLeft: 300, offsetWidth: 50 })).toBe(130);
    expect(centredScrollLeft(nav, { offsetLeft: 200, offsetWidth: 50 })).toBe(30);
  });

  it("never scrolls past either end", () => {
    expect(centredScrollLeft(nav, { offsetLeft: 10, offsetWidth: 80 })).toBe(0);
    expect(centredScrollLeft(nav, { offsetLeft: 470, offsetWidth: 50 })).toBe(130);
  });
});

describe("TabBar", () => {
  it("marks the current page and fades the edges that hide more tabs", () => {
    render(
      <MemoryRouter initialEntries={["/keys"]}>
        <TabBar tabs={TABS} />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(screen.getByRole("link", { name: "Keys" })).toHaveAttribute("aria-current", "page");
    expect(nav).not.toHaveClass("tabs--more-before", "tabs--more-after");

    setScrollBox(nav, { scrollLeft: 0, scrollWidth: 500, clientWidth: 390 });
    fireEvent.scroll(nav);
    expect(nav).toHaveClass("tabs--more-after");
    expect(nav).not.toHaveClass("tabs--more-before");

    setScrollBox(nav, { scrollLeft: 110, scrollWidth: 500, clientWidth: 390 });
    fireEvent.scroll(nav);
    expect(nav).toHaveClass("tabs--more-before");
    expect(nav).not.toHaveClass("tabs--more-after");
  });
});
