import { describe, expect, it } from "vitest";

import { firstInvalidField, type HideFormInput, validateHideForm } from "./hideValidation";

function aValidForm(overrides: Partial<HideFormInput> = {}): HideFormInput {
  return {
    hasCover: true,
    messageBytes: 10,
    capacityBytes: 100,
    method: "password",
    password: "a long passphrase",
    confirmPassword: "a long passphrase",
    recipientKey: "",
    recipientKeyProblem: null,
    ...overrides,
  };
}

describe("validateHideForm", () => {
  it("accepts a complete password form", () => {
    expect(validateHideForm(aValidForm())).toEqual({});
  });

  it("requires a cover and a message", () => {
    const errors = validateHideForm(aValidForm({ hasCover: false, messageBytes: 0 }));

    expect(Object.keys(errors)).toEqual(["cover", "message"]);
  });

  it("explains when the message is larger than the cover can hold", () => {
    const errors = validateHideForm(aValidForm({ messageBytes: 150, capacityBytes: 100 }));

    expect(errors.message).toContain("150 bytes");
    expect(errors.message).toContain("100 bytes");
  });

  it("does not judge capacity before it is known", () => {
    expect(validateHideForm(aValidForm({ messageBytes: 10_000, capacityBytes: null }))).toEqual({});
  });

  it("rejects mismatched password confirmation", () => {
    const errors = validateHideForm(aValidForm({ confirmPassword: "different" }));

    expect(errors).toEqual({ confirmPassword: "The passwords don't match." });
  });

  it("requires a recipient key for public-key protection", () => {
    const errors = validateHideForm(aValidForm({ method: "public_key", password: "" }));

    expect(errors).toEqual({ recipientKey: "Paste the recipient's public key." });
  });

  it("surfaces the server's verdict on an invalid recipient key", () => {
    const errors = validateHideForm(
      aValidForm({ method: "public_key", recipientKey: "junk", recipientKeyProblem: "Not a valid key." }),
    );

    expect(errors.recipientKey).toBe("Not a valid key.");
  });
});

describe("firstInvalidField", () => {
  it("returns the earliest field on the page", () => {
    expect(firstInvalidField({ password: "x", cover: "y" })).toBe("cover");
  });
});
