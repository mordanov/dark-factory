import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TicketCard } from "../../src/components/tickets/TicketCard";
import type { TicketResponse } from "../../src/types";

const base: TicketResponse = {
  id: "t1",
  display_id: "DEMO-0001",
  number: 1,
  project_id: "p1",
  parent_ticket_id: null,
  title: "Fix login bug",
  description: null,
  status: "OPEN",
  ticket_type: "bug",
  ticket_spec: "backend",
  urgent: false,
  blocker: false,
  bugfix: false,
  created_by: { id: "u1", email: "admin@example.com", role: "administrator" },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  assignees: [],
  follow_up_count: 0,
  tags: [],
};

function renderCard(ticket: Partial<TicketResponse> = {}) {
  return render(
    <MemoryRouter>
      <TicketCard ticket={{ ...base, ...ticket }} />
    </MemoryRouter>
  );
}

describe("TicketCard", () => {
  it("renders ticket title as a link", () => {
    renderCard();
    expect(screen.getByRole("link", { name: "Fix login bug" })).toHaveAttribute("href", "/tickets/t1");
  });

  it("shows status badge", () => {
    renderCard({ status: "IN_PROGRESS" });
    expect(screen.getByText("In Progress")).toBeInTheDocument();
  });

  it("shows assignee email prefix", () => {
    renderCard({
      assignees: [{ user_id: "u2", email: "alice@example.com", has_progress_update: false }],
    });
    expect(screen.getByText("alice")).toBeInTheDocument();
  });

  it("shows tags when present", () => {
    renderCard({
      tags: [{ id: "tag1", name: "frontend" }],
    });
    expect(screen.getByText("frontend")).toBeInTheDocument();
  });

  it("shows urgent flag badge when urgent is true", () => {
    renderCard({ urgent: true });
    expect(screen.getByText("URGENT")).toBeInTheDocument();
  });

  it("shows display_id badge when present", () => {
    renderCard({ display_id: "DEMO-0001" });
    expect(screen.getByText("DEMO-0001")).toBeInTheDocument();
  });
});
