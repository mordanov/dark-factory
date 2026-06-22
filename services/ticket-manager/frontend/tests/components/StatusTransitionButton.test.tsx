import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatusTransitionButton } from "../../src/components/tickets/StatusTransitionButton";
import * as ticketsApi from "../../src/api/tickets";
import type { TicketResponse, TransitionBlockedError } from "../../src/types";

const baseTicket: TicketResponse = {
  id: "t1",
  display_id: null,
  number: null,
  project_id: "p1",
  parent_ticket_id: null,
  title: "Some ticket",
  description: null,
  status: "OPEN",
  ticket_type: "feature",
  ticket_spec: null,
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

describe("StatusTransitionButton", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows next status buttons for OPEN ticket", () => {
    render(<StatusTransitionButton ticket={baseTicket} onTransitioned={vi.fn()} />);
    expect(screen.getByRole("button", { name: /in progress/i })).toBeInTheDocument();
  });

  it("shows no transitions for CLOSED ticket", () => {
    render(
      <StatusTransitionButton
        ticket={{ ...baseTicket, status: "CLOSED" }}
        onTransitioned={vi.fn()}
      />
    );
    expect(screen.getByText(/no further transitions/i)).toBeInTheDocument();
  });

  it("calls onTransitioned on successful transition", async () => {
    const updated: TicketResponse = { ...baseTicket, status: "IN_PROGRESS" };
    vi.spyOn(ticketsApi, "transitionTicket").mockResolvedValue(updated);
    const onTransitioned = vi.fn();
    const user = userEvent.setup();
    render(<StatusTransitionButton ticket={baseTicket} onTransitioned={onTransitioned} />);
    await user.click(screen.getByRole("button", { name: /in progress/i }));
    await waitFor(() => expect(onTransitioned).toHaveBeenCalledWith(updated));
  });

  it("shows blocked error with missing user list on 422", async () => {
    const blocked: TransitionBlockedError = {
      detail: "Transition blocked: not all assignees have submitted progress updates",
      missing_updates: [{ user_id: "u2", email: "bob@example.com" }],
    };
    vi.spyOn(ticketsApi, "transitionTicket").mockResolvedValue(blocked);
    const user = userEvent.setup();
    render(<StatusTransitionButton ticket={baseTicket} onTransitioned={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /in progress/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText("bob@example.com")).toBeInTheDocument();
  });
});
