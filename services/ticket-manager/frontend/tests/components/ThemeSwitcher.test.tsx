import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeSwitcher } from "../../src/components/common/ThemeSwitcher";

describe("ThemeSwitcher", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders swatch buttons for all six themes", () => {
    render(<ThemeSwitcher />);
    expect(screen.getByTitle("Light")).toBeInTheDocument();
    expect(screen.getByTitle("Dark")).toBeInTheDocument();
    expect(screen.getByTitle("Solarized")).toBeInTheDocument();
    expect(screen.getByTitle("Oceanic")).toBeInTheDocument();
    expect(screen.getByTitle("High Contrast")).toBeInTheDocument();
    expect(screen.getByTitle("Warm")).toBeInTheDocument();
  });

  it("marks the active theme swatch with aria-pressed=true", () => {
    render(<ThemeSwitcher />);
    // default theme is "light" when localStorage is empty
    expect(screen.getByTitle("Light")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTitle("Dark")).toHaveAttribute("aria-pressed", "false");
  });

  it("reads stored theme from localStorage", () => {
    localStorage.setItem("theme", "dark");
    render(<ThemeSwitcher />);
    expect(screen.getByTitle("Dark")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTitle("Light")).toHaveAttribute("aria-pressed", "false");
  });

  it("writes to localStorage and updates data-theme on click", async () => {
    const user = userEvent.setup();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    render(<ThemeSwitcher />);
    await user.click(screen.getByTitle("Dark"));
    expect(setItem).toHaveBeenCalledWith("theme", "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("renders a group with accessible label", () => {
    render(<ThemeSwitcher />);
    expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();
  });
});
