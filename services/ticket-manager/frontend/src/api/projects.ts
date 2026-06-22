import { apiClient } from "./client";
import type { ProjectSummary, TicketListResponse } from "../types";

export async function listProjects(): Promise<ProjectSummary[]> {
  const { data } = await apiClient.get<{ items: ProjectSummary[] }>("/projects");
  return data.items;
}

export async function createProject(body: { name: string; code: string }): Promise<ProjectSummary> {
  const { data } = await apiClient.post<ProjectSummary>("/projects", body);
  return data;
}

export async function listTickets(
  projectId: string,
  params?: { status?: string; assignee_id?: string; page?: number; page_size?: number }
): Promise<TicketListResponse> {
  const { data } = await apiClient.get<TicketListResponse>(
    `/projects/${projectId}/tickets`,
    { params }
  );
  return data;
}

const MAX_PAGE_SIZE = 100;

export async function listAllTickets(
  projectId: string,
  params?: { status?: string; assignee_id?: string }
): Promise<TicketListResponse> {
  const first = await listTickets(projectId, { ...params, page: 1, page_size: MAX_PAGE_SIZE });
  if (first.items.length >= first.total) return first;

  const totalPages = Math.ceil(first.total / MAX_PAGE_SIZE);
  const rest = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, i) =>
      listTickets(projectId, { ...params, page: i + 2, page_size: MAX_PAGE_SIZE })
    )
  );
  return { items: [first, ...rest].flatMap((r) => r.items), total: first.total };
}
