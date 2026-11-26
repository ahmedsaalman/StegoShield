import { type ReactNode, useEffect } from "react";

const APP_NAME = "StegoShield";

interface PageHeaderProps {
  title: string;
  description: ReactNode;
  /** Short mono label above the title, e.g. "Send". */
  eyebrow?: string;
  /** Decorative illustration shown beside the title on wide screens. */
  art?: ReactNode;
}

/** Full-width title band at the top of a page. */
export function PageHeader({ title, description, eyebrow, art }: PageHeaderProps) {
  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
  }, [title]);

  return (
    <header className="page-header">
      <div className="container page-header__inner">
        <div className="page-header__text">
          {eyebrow && <p className="page-header__eyebrow">{eyebrow}</p>}
          {/* tabIndex lets the layout move focus here after navigation, for screen-reader users. */}
          <h1 className="page-header__title" tabIndex={-1}>
            {title}
          </h1>
          <p className="page-header__description">{description}</p>
        </div>
        {art && (
          <div className="page-header__art" aria-hidden="true">
            {art}
          </div>
        )}
      </div>
    </header>
  );
}

interface PageBodyProps {
  children: ReactNode;
  /** Forms read best at a narrower width. */
  isNarrow?: boolean;
}

export function PageBody({ children, isNarrow = false }: PageBodyProps) {
  return <div className={isNarrow ? "container page-body page-body--narrow" : "container page-body"}>{children}</div>;
}
