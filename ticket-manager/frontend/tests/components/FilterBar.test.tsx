/**
 * FilterBar tests — updated for shadcn <Select> (T028 migration).
 * shadcn Select renders a button (SelectTrigger), not a native <select>.
 * Options appear in a listbox that opens on click/keyboard.
 *
 * Functional equivalence to pre-migration behavior is preserved:
 * - onChange fires with correct status/assigneeId values
 * - Assignee filter absent when no assignees
 * - All status options available in the dropdown
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterBar } from "../../src/components/common/FilterBar";
import type { FilterState } from "../../src/components/common/FilterBar";
import type { AssigneeSummary } from "../../src/types";

const noop = () => {};
const emptyFilters: FilterState = { status: "", assigneeId: "" };

const assignees: AssigneeSummary[] = [
  { user_id: "u1", email: "alice@example.com", has_progress_update: true },
  { user_id: "u2", email: "bob@example.com", has_progress_update: false },
];

describe("FilterBar", () => {
  it("renders status filter with accessible label", () => {
    render(<FilterBar filters={emptyFilters} assignees={[]} onChange={noop} />);
    // shadcn SelectTrigger is linked to Label via htmlFor/id
    expect(screen.getByLabelText("Status")).toBeInTheDocument();
  });

  it("does not render assignee filter when assignees is empty", () => {
    render(<FilterBar filters={emptyFilters} assignees={[]} onChange={noop} />);
    expect(screen.queryByLabelText("Assignee")).not.toBeInTheDocument();
  });

  it("renders assignee filter when assignees provided", () => {
    render(<FilterBar filters={emptyFilters} assignees={assignees} onChange={noop} />);
    expect(screen.getByLabelText("Assignee")).toBeInTheDocument();
  });

  it("status select options visible after opening trigger", async () => {
    const user = userEvent.setup();
    render(<FilterBar filters={emptyFilters} assignees={[]} onChange={noop} />);
    await user.click(screen.getByLabelText("Status"));
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "All statuses" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "In Progress" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Open" })).toBeInTheDocument();
    });
  });

  it("calls onChange with correct status when option selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<FilterBar filters={emptyFilters} assignees={[]} onChange={onChange} />);
    // Open the status select
    await user.click(screen.getByLabelText("Status"));
    // Click the "In Progress" option
    await waitFor(() => screen.getByRole("option", { name: "In Progress" }));
    await user.click(screen.getByRole("option", { name: "In Progress" }));
    expect(onChange).toHaveBeenCalledWith({ status: "IN_PROGRESS", assigneeId: "" });
  });

  it("calls onChange with empty status when 'All statuses' selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <FilterBar filters={{ status: "OPEN", assigneeId: "" }} assignees={[]} onChange={onChange} />
    );
    await user.click(screen.getByLabelText("Status"));
    await waitFor(() => screen.getByRole("option", { name: "All statuses" }));
    await user.click(screen.getByRole("option", { name: "All statuses" }));
    expect(onChange).toHaveBeenCalledWith({ status: "", assigneeId: "" });
  });

  it("calls onChange with correct assigneeId when assignee selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<FilterBar filters={emptyFilters} assignees={assignees} onChange={onChange} />);
    await user.click(screen.getByLabelText("Assignee"));
    await waitFor(() => screen.getByRole("option", { name: "alice@example.com" }));
    await user.click(screen.getByRole("option", { name: "alice@example.com" }));
    expect(onChange).toHaveBeenCalledWith({ status: "", assigneeId: "u1" });
  });
});
