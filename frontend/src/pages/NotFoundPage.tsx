import { Link, useLocation } from "react-router-dom";

import { MAIN_TABS } from "../components/navigation";
import { PageBody, PageHeader } from "../components/PageHeader";

export function NotFoundPage() {
  const { pathname } = useLocation();
  return (
    <>
      <PageHeader
        eyebrow="404"
        title="Page not found"
        description={
          <>
            There&apos;s no page at <code>{pathname}</code>. It may have been mistyped; every page is listed below.
          </>
        }
      />
      <PageBody>
        <nav className="actions" aria-label="All pages">
          {MAIN_TABS.map((tab, index) => (
            <Link key={tab.to} to={tab.to} className={index === 0 ? "btn btn--primary" : "btn btn--secondary"}>
              {tab.label}
            </Link>
          ))}
        </nav>
      </PageBody>
    </>
  );
}
