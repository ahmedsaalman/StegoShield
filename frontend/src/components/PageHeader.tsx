import { type ReactNode, useEffect } from "react";

const APP_NAME = "StegoShield";

interface PageHeaderProps {
  title: string;
  description: ReactNode;
}

export function PageHeader({ title, description }: PageHeaderProps) {
  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
  }, [title]);

  return (
    <header className="page-header">
      {/* tabIndex lets the layout move focus here after navigation, for screen-reader users. */}
      <h1 className="page-header__title" tabIndex={-1}>
        {title}
      </h1>
      <p className="page-header__description">{description}</p>
    </header>
  );
}
