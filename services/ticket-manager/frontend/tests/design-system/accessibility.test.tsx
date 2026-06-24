/**
 * Accessibility regression tests (T020, FR-001, FR-002, FR-003, SC-001, SC-002)
 *
 * These tests verify ARIA requirements that must hold before AND after the
 * design system migration:
 *   - Icon-only buttons have aria-label
 *   - Form inputs are associated with labels
 *   - Interactive elements have accessible names
 *
 * Tests are written against the post-migration component API (shadcn primitives).
 * If a test fails because the component hasn't been migrated yet, it is noted.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// ─── TicketForm ───────────────────────────────────────────────────────────────

import { TicketForm } from "../../src/components/tickets/TicketForm";

const noop = () => {};

describe("TicketForm accessibility (FR-003)", () => {
  it("title input has an accessible label", () => {
    render(<TicketForm onSubmit={noop} />);
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
  });

  it("description input has an accessible label", () => {
    render(<TicketForm onSubmit={noop} />);
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  });

  it("submit button has an accessible name", () => {
    render(<TicketForm onSubmit={noop} />);
    expect(screen.getByRole("button", { name: /save|create|submit/i })).toBeInTheDocument();
  });

  it("cancel button has an accessible name when onCancel provided", () => {
    render(<TicketForm onSubmit={noop} onCancel={noop} />);
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });
});

// ─── ThemeSwitcher ────────────────────────────────────────────────────────────

import { ThemeSwitcher } from "../../src/components/common/ThemeSwitcher";

describe("ThemeSwitcher accessibility (FR-003)", () => {
  it("swatch buttons have accessible names (title attribute)", () => {
    render(<ThemeSwitcher />);
    // Each swatch must have a title so screen readers can identify it
    expect(screen.getByTitle("Light")).toBeInTheDocument();
    expect(screen.getByTitle("Dark")).toBeInTheDocument();
  });

  it("swatch group has accessible label", () => {
    render(<ThemeSwitcher />);
    expect(screen.getByRole("group", { name: /theme/i })).toBeInTheDocument();
  });

  it("active swatch has aria-pressed=true", () => {
    render(<ThemeSwitcher />);
    expect(screen.getByTitle("Light")).toHaveAttribute("aria-pressed", "true");
  });
});

// ─── FilterBar ────────────────────────────────────────────────────────────────

import { FilterBar } from "../../src/components/common/FilterBar";
import type { FilterState } from "../../src/components/common/FilterBar";

const emptyFilters: FilterState = { status: "", assigneeId: "" };

describe("FilterBar accessibility (FR-003)", () => {
  it("status filter has an accessible label", () => {
    render(<FilterBar filters={emptyFilters} assignees={[]} onChange={noop} />);
    // After migration, Status label might be a <Label> for a shadcn <Select>
    // For now (pre-migration), it's a native <select> with aria-label or <label>
    expect(screen.getByLabelText(/status/i)).toBeInTheDocument();
  });
});

// ─── LanguageSwitcher ─────────────────────────────────────────────────────────

import { LanguageSwitcher } from "../../src/components/common/LanguageSwitcher";

describe("LanguageSwitcher accessibility", () => {
  it("language buttons have accessible names", () => {
    render(<LanguageSwitcher />);
    expect(screen.getByRole("button", { name: "EN" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "RU" })).toBeInTheDocument();
  });

  it("active language has aria-pressed=true", () => {
    render(<LanguageSwitcher />);
    const en = screen.getByRole("button", { name: "EN" });
    expect(en).toHaveAttribute("aria-pressed", "true");
  });

  it("group has accessible label", () => {
    render(<LanguageSwitcher />);
    expect(screen.getByRole("group", { name: /language/i })).toBeInTheDocument();
  });
});

// LoginPage removed: authentication is now handled by Keycloak (redirect-based, no local login form)
