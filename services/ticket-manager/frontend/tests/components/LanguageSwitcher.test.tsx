import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LanguageSwitcher } from "../../src/components/common/LanguageSwitcher";

describe("LanguageSwitcher", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders EN, RU and ES buttons", () => {
    render(<LanguageSwitcher />);
    expect(screen.getByRole("button", { name: "EN" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "RU" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ES" })).toBeInTheDocument();
  });

  it("marks the active language with aria-pressed=true", () => {
    render(<LanguageSwitcher />);
    // test setup initialises i18n with "en"
    expect(screen.getByRole("button", { name: "EN" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "RU" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "ES" })).toHaveAttribute("aria-pressed", "false");
  });

  it("writes to localStorage when a language is selected", async () => {
    const user = userEvent.setup();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    render(<LanguageSwitcher />);
    await user.click(screen.getByRole("button", { name: "RU" }));
    expect(setItem).toHaveBeenCalledWith("lang", "ru");
  });

  it("renders a group with accessible label", () => {
    render(<LanguageSwitcher />);
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();
  });
});
