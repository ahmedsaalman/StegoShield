import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

export interface Tab {
  to: string;
  label: string;
  end?: boolean;
}

export interface ScrollEdges {
  hasMoreBefore: boolean;
  hasMoreAfter: boolean;
}

/** Sub-pixel scroll positions (zoom, high-DPI screens) shouldn't show a fade over nothing. */
const EDGE_TOLERANCE_PX = 2;

/** Which ends of a horizontally scrolling element still have content hidden past them. */
export function scrollEdges({
  scrollLeft,
  scrollWidth,
  clientWidth,
}: Pick<HTMLElement, "scrollLeft" | "scrollWidth" | "clientWidth">): ScrollEdges {
  return {
    hasMoreBefore: scrollLeft > EDGE_TOLERANCE_PX,
    hasMoreAfter: scrollLeft + clientWidth < scrollWidth - EDGE_TOLERANCE_PX,
  };
}

/** Scroll offset that centres `item` in `container`, clamped to the scrollable range. */
export function centredScrollLeft(
  container: Pick<HTMLElement, "clientWidth" | "scrollWidth">,
  item: Pick<HTMLElement, "offsetLeft" | "offsetWidth">,
): number {
  const centred = item.offsetLeft - (container.clientWidth - item.offsetWidth) / 2;
  return Math.max(0, Math.min(centred, container.scrollWidth - container.clientWidth));
}

/**
 * The main navigation. On narrow screens it scrolls sideways: the active tab is kept in view after
 * every navigation, and each edge fades out while more tabs are hidden past it.
 */
export function TabBar({ tabs }: { tabs: Tab[] }) {
  const navRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const [edges, setEdges] = useState<ScrollEdges>({ hasMoreBefore: false, hasMoreAfter: false });

  const updateEdges = useCallback(() => {
    const nav = navRef.current;
    if (!nav) return;
    const next = scrollEdges(nav);
    setEdges((previous) =>
      previous.hasMoreBefore === next.hasMoreBefore && previous.hasMoreAfter === next.hasMoreAfter ? previous : next,
    );
  }, []);

  useLayoutEffect(() => {
    const nav = navRef.current;
    const active = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (nav && active) nav.scrollLeft = centredScrollLeft(nav, active);
    updateEdges();
  }, [pathname, updateEdges]);

  useEffect(() => {
    window.addEventListener("resize", updateEdges);
    return () => window.removeEventListener("resize", updateEdges);
  }, [updateEdges]);

  const className = [
    "container",
    "tabs",
    edges.hasMoreBefore && "tabs--more-before",
    edges.hasMoreAfter && "tabs--more-after",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <nav ref={navRef} className={className} aria-label="Main" onScroll={updateEdges}>
      {tabs.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end={tab.end} className="tab">
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
