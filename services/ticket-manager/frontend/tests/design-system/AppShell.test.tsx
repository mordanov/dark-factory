/**
 * Tests for T015: AppShell layout component
 * - Skip-to-content link must be present and focusable (FR-001, SC-001)
 * - Main content has id="main-content" (skip link target)
 * - aria-live region for status announcements (T021, FR-005)
 * - Children rendered inside <main>
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../../src/components/layout/AppShell";

// Navbar imports useAuthStore and useTheme — provide minimal mocks
vi.mock("../../src/store/auth", () => ({
  useAuthStore: (selector: (s: object) => unknown) => selector({ currentUser: null, logout: vi.fn() }),
}));
vi.mock("../../src/hooks/useTheme", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));

function renderShell(content = <p>Page content</p>) {
  return render(
    <MemoryRouter>
      <AppShell>{content}</AppShell>
    </MemoryRouter>
  );
}

describe("AppShell (T015)", () => {
  it("renders children inside <main> with id=main-content", () => {
    renderShell();
    const main = document.getElementById("main-content");
    expect(main).not.toBeNull();
    expect(main?.tagName).toBe("MAIN");
    expect(screen.getByText("Page content")).toBeInTheDocument();
  });

  it("renders skip-to-content link targeting #main-content", () => {
    renderShell();
    const skipLink = screen.getByRole("link", { name: /skip to content/i });
    expect(skipLink).toBeInTheDocument();
    expect(skipLink).toHaveAttribute("href", "#main-content");
  });

  it("skip-to-content link has sr-only class (visually hidden by default)", () => {
    renderShell();
    const skipLink = screen.getByRole("link", { name: /skip to content/i });
    expect(skipLink.className).toContain("sr-only");
  });

  it("skip-to-content link is the first interactive element (Tab #1)", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.tab();
    const skipLink = screen.getByRole("link", { name: /skip to content/i });
    expect(skipLink).toHaveFocus();
  });

  it("renders aria-live polite region for status announcements (T021)", () => {
    renderShell();
    const announcer = document.getElementById("status-announcer");
    expect(announcer).not.toBeNull();
    expect(announcer).toHaveAttribute("aria-live", "polite");
    expect(announcer?.className).toContain("sr-only");
  });

  it("aria-live region is initially empty", () => {
    renderShell();
    const announcer = document.getElementById("status-announcer");
    expect(announcer?.textContent?.trim()).toBe("");
  });
});
