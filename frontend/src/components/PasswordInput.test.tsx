import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PasswordInput } from "./PasswordInput";

function renderInput() {
  render(
    <>
      <label htmlFor="pw">Password</label>
      <PasswordInput id="pw" value="" onChange={() => undefined} autoComplete="off" />
    </>,
  );
  return screen.getByLabelText("Password");
}

describe("PasswordInput", () => {
  it("warns while Caps Lock is on", async () => {
    const user = userEvent.setup();
    const input = renderInput();

    await user.click(input);
    await user.keyboard("{CapsLock}");

    expect(screen.getByRole("status")).toHaveTextContent("Caps Lock is on");
  });

  it("stays quiet when Caps Lock is off", async () => {
    const user = userEvent.setup();
    const input = renderInput();

    await user.click(input);
    await user.keyboard("a");

    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });
});
