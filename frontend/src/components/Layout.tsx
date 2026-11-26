import { useEffect, useEffectEvent, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useAppState } from "../state/AppState";
import { Icon, type IconName } from "./Icon";
import { ThemeToggle } from "./ThemeToggle";

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
}

const NAV_GROUPS: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Send",
    items: [
      { to: "/preflight", label: "Pre-flight check", icon: "gauge" },
      { to: "/hide", label: "Hide a message", icon: "hide" },
    ],
  },
  { heading: "Receive", items: [{ to: "/reveal", label: "Reveal a message", icon: "reveal" }] },
  { heading: "Analyse", items: [{ to: "/detect", label: "Detect hidden data", icon: "scan" }] },
  { heading: "Set up", items: [{ to: "/keys", label: "Keys", icon: "key" }] },
];

export function Layout() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  useFocusHeadingOnNavigation(() => setIsMenuOpen(false));

  useEffect(() => {
    if (!isMenuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && setIsMenuOpen(false);
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isMenuOpen]);

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="topbar">
        <Brand />
        <button
          type="button"
          className="topbar__menu"
          aria-expanded={isMenuOpen}
          aria-controls="site-nav"
          onClick={() => setIsMenuOpen((open) => !open)}
        >
          <Icon name={isMenuOpen ? "close" : "menu"} />
          <span>Menu</span>
        </button>
      </header>
      <aside className={isMenuOpen ? "sidebar sidebar--open" : "sidebar"}>
        <div className="sidebar__brand">
          <Brand />
        </div>
        <SiteNav />
        <div className="sidebar__footer">
          <ThemeToggle />
        </div>
      </aside>
      <main id="main" className="main" tabIndex={-1}>
        <div className="main__content">
          <Outlet />
        </div>
        <SiteFooter />
      </main>
    </div>
  );
}

function Brand() {
  return (
    <Link to="/" className="brand">
      <Icon name="shield" size={26} className="brand__icon" />
      <span className="brand__name">StegoShield</span>
    </Link>
  );
}

function SiteNav() {
  return (
    <nav id="site-nav" aria-label="Main">
      {NAV_GROUPS.map((group) => (
        <div key={group.heading} className="nav-group">
          <p className="nav-group__heading">{group.heading}</p>
          <ul className="nav-group__list">
            {group.items.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} className="nav-link">
                  <Icon name={item.icon} />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SiteFooter() {
  const { meta } = useAppState();
  return (
    <footer className="site-footer">
      <p>
        <Icon name="lock" size={16} /> Nothing you upload is stored. Images, messages and keys are processed in
        memory and discarded after each request.
      </p>
      {meta && (
        <p className="text-muted">
          Version {meta.version} · Detector: {meta.detector.available ? meta.detector.model_type : "not installed"} ·{" "}
          <a href="/api/docs">API documentation</a>
        </p>
      )}
    </footer>
  );
}

/** After client-side navigation, move focus to the new page's heading so screen readers announce it. */
function useFocusHeadingOnNavigation(onNavigate: () => void) {
  const { pathname } = useLocation();
  const isFirstRender = useRef(true);
  const handleNavigate = useEffectEvent(onNavigate);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    handleNavigate();
    document.querySelector<HTMLElement>("main h1")?.focus();
    window.scrollTo({ top: 0 });
  }, [pathname]);
}
