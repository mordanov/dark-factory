import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AdminUsersPage } from "../../src/pages/AdminUsersPage";
import * as adminApi from "../../src/api/admin";
import type { AdminUserListResponse } from "../../src/types";

vi.mock("../../src/store/auth", () => ({
  useAuthStore: vi.fn((selector: (s: unknown) => unknown) =>
    selector({ currentUser: { id: "u1", email: "admin@example.com", role: "administrator" } })
  ),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const users: AdminUserListResponse = {
  total: 2,
  items: [
    { id: "u1", email: "admin@example.com", role: "administrator", created_at: new Date().toISOString(), blocked_at: null },
    { id: "u2", email: "alice@example.com", role: "user", created_at: new Date().toISOString(), blocked_at: null },
  ],
};

describe("AdminUsersPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders page title", () => {
    vi.spyOn(adminApi, "listAdminUsers").mockResolvedValue(users);
    render(<AdminUsersPage />, { wrapper });
    expect(screen.getByText("User Management")).toBeInTheDocument();
  });

  it("shows loading state initially", () => {
    vi.spyOn(adminApi, "listAdminUsers").mockResolvedValue(users);
    render(<AdminUsersPage />, { wrapper });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders user rows when data loads", async () => {
    vi.spyOn(adminApi, "listAdminUsers").mockResolvedValue(users);
    render(<AdminUsersPage />, { wrapper });
    await waitFor(() => expect(screen.getByText("alice@example.com")).toBeInTheDocument());
    expect(screen.getByText("admin@example.com")).toBeInTheDocument();
  });

  it("opens user form when New User is clicked", async () => {
    vi.spyOn(adminApi, "listAdminUsers").mockResolvedValue(users);
    const user = userEvent.setup();
    render(<AdminUsersPage />, { wrapper });
    await user.click(screen.getByRole("button", { name: "+ New User" }));
    expect(screen.getByText("Create User")).toBeInTheDocument();
  });
});
