import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { NotFoundPage } from "./NotFoundPage";

describe("NotFoundPage", () => {
  it("names the missing address and links to every page", () => {
    render(
      <MemoryRouter initialEntries={["/hdie"]}>
        <NotFoundPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("/hdie")).toBeInTheDocument();
    const pages = within(screen.getByRole("navigation", { name: "All pages" }));
    expect(pages.getByRole("link", { name: "Hide" })).toHaveAttribute("href", "/hide");
    expect(pages.getAllByRole("link")).toHaveLength(7);
  });
});
