import { Link } from "react-router-dom";

import { PageHeader } from "../components/PageHeader";

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" description="That address doesn't match any page in StegoShield." />
      <p>
        <Link to="/">Go to the home page</Link>
      </p>
    </>
  );
}
