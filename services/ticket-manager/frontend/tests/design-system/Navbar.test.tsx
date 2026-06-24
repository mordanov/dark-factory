/**
 * Tests for T014: Navbar layout component
 * - Dark mode toggle button with aria-label="Toggle dark mode" (FR-001, SC-001)
 * - Nav links (Projects, Admin) present with correct hrefs
 * - Admin link gated by role
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Navbar } from "../../src/components/layout/Navbar";

const mockSetTheme = vi.fn();

// Module-level mocks apply to all tests in this file
vi.mock("../../src/hooks/useTheme", () => ({
  useTheme: () => ({ theme: "light", setTheme: mockSetTheme }),
}));

// Auth store mock — overridden per-describe via direct mutation where needed
const mockAuthState = {
  user: { sub: "u1", email: "dev@example.com", username: "dev", isAdmin: false },
  logout: vi.fn(),
};
vi.mock("../../src/store/auth", () => ({
  useAuthStore: (selector: (s: typeof mockAuthState) => unknown) => selector(mockAuthState),
}));

// Keycloak admin console URL
vi.stubEnv("VITE_KEYCLOAK_URL", "http://keycloak:8080");

function renderNavbar() {
  return render(<MemoryRouter><Navbar /></MemoryRouter>);
}

describe("Navbar (T014)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to non-admin user
    mockAuthState.user = { sub: "u1", email: "dev@example.com", username: "dev", isAdmin: false };
  });

  it("renders dark mode toggle button with aria-label 'Toggle dark mode'", () => {
    renderNavbar();
    expect(screen.getByRole("button", { name: "Toggle dark mode" })).toBeInTheDocument();
  });

  it("dark mode toggle contains an SVG icon", () => {
    renderNavbar();
    const toggle = screen.getByRole("button", { name: "Toggle dark mode" });
    expect(toggle.querySelector("svg")).toBeInTheDocument();
  });

  it("clicking dark mode toggle calls setTheme with 'dark' (from light)", async () => {
    const user = userEvent.setup();
    renderNavbar();
    await user.click(screen.getByRole("button", { name: "Toggle dark mode" }));
    expect(mockSetTheme).toHaveBeenCalledWith("dark");
    expect(mockSetTheme).toHaveBeenCalledTimes(1);
  });

  it("renders nav link to /projects", () => {
    renderNavbar();
    const link = screen.getByRole("link", { name: "Projects" });
    expect(link).toHaveAttribute("href", "/projects");
  });

  it("hides admin link for non-administrator role", () => {
    renderNavbar();
    expect(screen.queryByRole("link", { name: /admin/i })).not.toBeInTheDocument();
  });

  it("shows admin link for administrator role", () => {
    mockAuthState.user = { sub: "u1", email: "admin@example.com", username: "admin", isAdmin: true };
    renderNavbar();
    const adminLink = screen.getByRole("link", { name: /admin/i });
    expect(adminLink).toHaveAttribute("href", expect.stringContaining("/admin/dark-factory/console"));
  });

  it("dark mode toggle is keyboard-operable (Enter key)", async () => {
    const user = userEvent.setup();
    renderNavbar();
    const toggle = screen.getByRole("button", { name: "Toggle dark mode" });
    toggle.focus();
    await user.keyboard("{Enter}");
    expect(mockSetTheme).toHaveBeenCalledWith("dark");
  });
});
