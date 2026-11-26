import { Link } from "react-router-dom";

import { PageBody, PageHeader } from "../components/PageHeader";

export function NotFoundPage() {
  return (
    <>
      <PageHeader eyebrow="404" title="Page not found" description="That address doesn't match any page in StegoShield." />
      <PageBody>
        <Link to="/" className="btn btn--secondary">
          Back to overview
        </Link>
      </PageBody>
    </>
  );
}
