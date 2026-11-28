import { useEffect, useEffectEvent, useRef } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { useAppState } from "../state/AppState";
import { Icon } from "./Icon";
import { type Tab, TabBar } from "./TabBar";
import { ThemeSwitcher } from "./ThemeToggle";

const TABS: Tab[] = [
  { to: "/", label: "Overview", end: true },
  { to: "/preflight", label: "Pre-flight" },
  { to: "/hide", label: "Hide" },
  { to: "/reveal", label: "Reveal" },
  { to: "/detect", label: "Detect" },
  { to: "/keys", label: "Keys" },
  { to: "/lab", label: "Lab" },
];

export function Layout() {
  useFocusHeadingOnNavigation();
  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <SiteHeader />
      <main id="main" className="main" tabIndex={-1}>
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  );
}

function SiteHeader() {
  const { meta } = useAppState();
  return (
    <header className="site-header">
      <div className="container site-header__bar">
        <Link to="/" className="brand">
          <span className="brand__mark" aria-hidden="true">
            <Icon name="shield" size={15} />
          </span>
          StegoShield
          {meta && <span className="version">v{meta.version}</span>}
        </Link>
        <div className="site-header__actions">
          <a className="btn btn--ghost btn--sm" href="/api/docs">
            API docs
          </a>
        </div>
      </div>
      <TabBar tabs={TABS} />
    </header>
  );
}

function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <p className="site-footer__privacy">
          <Icon name="lock" />
          Stateless: nothing you upload is stored.
        </p>
        <div className="site-footer__end">
          <ServerStatus />
          <ThemeSwitcher />
        </div>
      </div>
    </footer>
  );
}

/** Whether the API answered at start-up and, if it did, whether its detector is installed. */
function ServerStatus() {
  const { meta, metaError } = useAppState();
  if (metaError) {
    return (
      <span className="status-dot status-dot--danger" title={metaError.message}>
        Server unreachable
      </span>
    );
  }
  if (!meta) return null;
  return meta.detector.available ? (
    <span className="status-dot status-dot--success">Detector ready</span>
  ) : (
    <span className="status-dot status-dot--warning">Detector unavailable</span>
  );
}

/** After client-side navigation, move focus to the new page's heading so screen readers announce it. */
function useFocusHeadingOnNavigation() {
  const { pathname } = useLocation();
  const isFirstRender = useRef(true);
  const focusHeading = useEffectEvent(() => {
    document.querySelector<HTMLElement>("main h1")?.focus();
    window.scrollTo({ top: 0 });
  });

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    focusHeading();
  }, [pathname]);
}
