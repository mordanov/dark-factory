import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProjectPage } from "../../src/pages/ProjectPage";

vi.mock("../../src/components/projects/ProjectTicketList", () => ({
  ProjectTicketList: () => <div data-testid="ticket-list" />,
}));
vi.mock("../../src/components/projects/KanbanBoard", () => ({
  KanbanBoard: () => <div data-testid="kanban-board" />,
}));
vi.mock("../../src/api/projects", () => ({
  listProjects: () => Promise.resolve([]),
  listTickets: () => Promise.resolve({ items: [], total: 0 }),
}));

function renderPage(initialEntry = "/projects/p1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/projects/:projectId" element={<ProjectPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ProjectPage URL persistence", () => {
  afterEach(() => vi.restoreAllMocks());

  it("defaults to list view when no query param is present", () => {
    renderPage("/projects/p1");
    expect(screen.getByTestId("ticket-list")).toBeInTheDocument();
    expect(screen.queryByTestId("kanban-board")).not.toBeInTheDocument();
  });

  it("shows board view when ?view=board is in the URL", () => {
    renderPage("/projects/p1?view=board");
    expect(screen.getByTestId("kanban-board")).toBeInTheDocument();
    expect(screen.queryByTestId("ticket-list")).not.toBeInTheDocument();
  });

  it("switches to board view when board button is clicked", async () => {
    const user = userEvent.setup();
    renderPage("/projects/p1");
    expect(screen.getByTestId("ticket-list")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "⊞ Board" }));
    expect(screen.getByTestId("kanban-board")).toBeInTheDocument();
    expect(screen.queryByTestId("ticket-list")).not.toBeInTheDocument();
  });

  it("switches back to list view when list button is clicked", async () => {
    const user = userEvent.setup();
    renderPage("/projects/p1?view=board");
    await user.click(screen.getByRole("button", { name: "☰ List" }));
    expect(screen.getByTestId("ticket-list")).toBeInTheDocument();
    expect(screen.queryByTestId("kanban-board")).not.toBeInTheDocument();
  });
});
