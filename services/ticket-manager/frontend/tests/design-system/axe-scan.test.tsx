/**
 * SC-002: Zero axe-core accessibility violations across all 5 application pages.
 *
 * Pages tested:
 *  1. LoginPage
 *  2. ProjectListPage
 *  3. ProjectPage  (with projectId route param)
 *  4. TicketDetailPage (with ticketId route param)
 *  5. AdminUsersPage
 */
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

// ── Global mocks ──────────────────────────────────────────────────────────────

vi.mock("../../src/store/auth", () => ({
  useAuthStore: (selector: (s: object) => unknown) =>
    selector({
      currentUser: { id: "u1", email: "admin@example.com", role: "administrator" },
      login: vi.fn(),
      logout: vi.fn(),
    }),
}));

vi.mock("../../src/api/auth", () => ({ login: vi.fn() }));

const MOCK_PROJECTS = [
  {
    id: "p1",
    name: "Test Project",
    code: "ABCD-123",
    created_at: "2024-01-01T00:00:00Z",
    ticket_counts: { open: 1, active: 2, done: 3 },
  },
];

vi.mock("../../src/api/projects", () => ({
  listProjects: () => Promise.resolve(MOCK_PROJECTS),
  listTickets: () => Promise.resolve({ items: [], total: 0 }),
  createProject: vi.fn(),
}));

const MOCK_TICKET = {
  id: "t1",
  title: "Accessibility test ticket",
  description: "A ticket for accessibility testing",
  status: "OPEN",
  ticket_type: "FEATURE",
  ticket_spec: null,
  urgent: false,
  blocker: false,
  bugfix: false,
  tags: [],
  assignees: [],
  created_by: { id: "u1", email: "admin@example.com" },
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  project_id: "p1",
};

vi.mock("../../src/api/tickets", () => ({
  getTicket: () => Promise.resolve(MOCK_TICKET),
  listProgress: () => Promise.resolve([]),
  listTicketEvents: () => Promise.resolve([]),
  createTicket: vi.fn(),
  updateTicket: vi.fn(),
  deleteTicket: vi.fn(),
  submitProgress: vi.fn(),
  createFollowUp: vi.fn(),
  assignUser: vi.fn(),
  unassignUser: vi.fn(),
  addTag: vi.fn(),
  removeTag: vi.fn(),
}));

const MOCK_ADMIN_USERS_LIST = {
  items: [
    { id: "u1", email: "admin@example.com", role: "administrator", is_blocked: false },
    { id: "u2", email: "user@example.com", role: "user", is_blocked: false },
  ],
};

vi.mock("../../src/api/admin", () => ({
  listAdminUsers: () => Promise.resolve(MOCK_ADMIN_USERS_LIST),
  createAdminUser: vi.fn(),
  updateAdminUser: vi.fn(),
  blockAdminUser: vi.fn(),
  unblockAdminUser: vi.fn(),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

// ── Page imports ──────────────────────────────────────────────────────────────

import { LoginPage } from "../../src/pages/LoginPage";
import { ProjectListPage } from "../../src/pages/ProjectListPage";
import { ProjectPage } from "../../src/pages/ProjectPage";
import { TicketDetailPage } from "../../src/pages/TicketDetailPage";
import { AdminUsersPage } from "../../src/pages/AdminUsersPage";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("SC-002: Zero axe violations on all 5 pages", () => {
  it("LoginPage has no axe violations", async () => {
    const { container } = render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("ProjectListPage has no axe violations", async () => {
    const qc = makeQC();
    qc.setQueryData(["projects"], MOCK_PROJECTS);
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ProjectListPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("ProjectPage has no axe violations", async () => {
    const qc = makeQC();
    qc.setQueryData(["projects"], MOCK_PROJECTS);
    qc.setQueryData(["tickets", "p1", {}], { items: [], total: 0 });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/projects/p1"]}>
          <Routes>
            <Route path="/projects/:projectId" element={<ProjectPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("TicketDetailPage has no axe violations", async () => {
    const qc = makeQC();
    qc.setQueryData(["ticket", "t1"], MOCK_TICKET);
    qc.setQueryData(["ticket-progress", "t1"], []);
    qc.setQueryData(["ticket-events", "t1"], []);
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/tickets/t1"]}>
          <Routes>
            <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("AdminUsersPage has no axe violations", async () => {
    const qc = makeQC();
    qc.setQueryData(["admin", "users"], MOCK_ADMIN_USERS_LIST);
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AdminUsersPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
