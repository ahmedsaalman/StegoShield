import type { Tab } from "./TabBar";

/** The main pages, in the order the tab bar shows them. */
export const MAIN_TABS: Tab[] = [
  { to: "/", label: "Overview", end: true },
  { to: "/preflight", label: "Pre-flight" },
  { to: "/hide", label: "Hide" },
  { to: "/reveal", label: "Reveal" },
  { to: "/detect", label: "Detect" },
  { to: "/keys", label: "Keys" },
  { to: "/lab", label: "Lab" },
];
