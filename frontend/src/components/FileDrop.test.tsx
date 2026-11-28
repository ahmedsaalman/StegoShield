import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FileDrop } from "./FileDrop";

/** jsdom has no DragEvent, so a MouseEvent of the same type carries `relatedTarget` to React's handler. */
function dragLeave(zone: HTMLElement, enteredElement: Element) {
  fireEvent(zone, new MouseEvent("dragleave", { bubbles: true, relatedTarget: enteredElement }));
}

function renderDrop() {
  render(<FileDrop label="Drop an image here" hint="PNG only" accept="image/png" onFile={vi.fn()} />);
  const title = screen.getByText("Drop an image here");
  // The zone is the drag target around the label; tests reach it the way the pointer does.
  const zone = title.closest(".file-drop");
  if (!(zone instanceof HTMLElement)) throw new Error("Drop zone not rendered");
  return { zone, title };
}

describe("FileDrop", () => {
  it("stays highlighted while the pointer moves over its own text", () => {
    const { zone, title } = renderDrop();

    fireEvent.dragOver(zone);
    dragLeave(zone, title);

    expect(zone).toHaveClass("file-drop--active");
  });

  it("drops the highlight when the pointer leaves the zone", () => {
    const { zone } = renderDrop();

    fireEvent.dragOver(zone);
    dragLeave(zone, document.body);

    expect(zone).not.toHaveClass("file-drop--active");
  });

  it("hands over a chosen file", () => {
    const onFile = vi.fn();
    render(<FileDrop label="Drop an image here" hint="PNG only" accept="image/png" onFile={onFile} />);
    const file = new File(["png"], "cover.png", { type: "image/png" });

    fireEvent.change(screen.getByLabelText(/Drop an image here/), { target: { files: [file] } });

    expect(onFile).toHaveBeenCalledWith(file);
  });
});
