import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TicketForm } from "../../src/components/tickets/TicketForm";

describe("TicketForm", () => {
  it("renders title and description fields", () => {
    render(<TicketForm onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  });

  it("shows validation error when title is empty", async () => {
    const user = userEvent.setup();
    render(<TicketForm onSubmit={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Title is required");
  });

  it("shows validation error when specification is not selected", async () => {
    const user = userEvent.setup();
    render(<TicketForm onSubmit={vi.fn()} />);
    await user.type(screen.getByLabelText(/title/i), "My ticket");
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Specification is required");
  });

  it("calls onSubmit with all form values", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<TicketForm onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText(/title/i), "  My ticket  ");
    // Radix Select: click trigger to open, then click the option by text
    await user.click(screen.getByLabelText(/specification/i));
    await user.click(screen.getByRole("option", { name: /backend/i }));
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "My ticket",
        description: null,
        ticket_spec: "backend",
        ticket_type: "feature",
        urgent: false,
        blocker: false,
        bugfix: false,
        tags: [],
      })
    );
  });

  it("calls onCancel when cancel button clicked", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<TicketForm onSubmit={vi.fn()} onCancel={onCancel} />);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("populates initial values for editing", () => {
    render(
      <TicketForm
        initialValues={{ title: "Existing title", description: "Some desc" }}
        onSubmit={vi.fn()}
      />
    );
    expect(screen.getByLabelText(/title/i)).toHaveValue("Existing title");
    expect(screen.getByLabelText(/description/i)).toHaveValue("Some desc");
  });
});
