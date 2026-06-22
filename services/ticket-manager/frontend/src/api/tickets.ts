import { apiClient } from "./client";
import type {
  TicketResponse,
  TicketCreate,
  TicketUpdate,
  AssignmentResponse,
  ProgressUpdateResponse,
  ProgressListResponse,
  TransitionBlockedError,
  TicketStatus,
  EventListResponse,
  TagResponse,
} from "../types";

export async function createTicket(
  projectId: string,
  data: TicketCreate
): Promise<TicketResponse> {
  const { data: ticket } = await apiClient.post<TicketResponse>(
    `/projects/${projectId}/tickets`,
    data
  );
  return ticket;
}

export async function createFollowUp(
  parentTicketId: string,
  data: TicketCreate
): Promise<TicketResponse> {
  const { data: ticket } = await apiClient.post<TicketResponse>(
    `/tickets/${parentTicketId}/follow-ups`,
    data
  );
  return ticket;
}

export async function getTicket(ticketId: string): Promise<TicketResponse> {
  const { data } = await apiClient.get<TicketResponse>(`/tickets/${ticketId}`);
  return data;
}

export async function updateTicket(
  ticketId: string,
  data: TicketUpdate
): Promise<TicketResponse> {
  const { data: ticket } = await apiClient.patch<TicketResponse>(
    `/tickets/${ticketId}`,
    data
  );
  return ticket;
}

export async function deleteTicket(ticketId: string): Promise<void> {
  await apiClient.delete(`/tickets/${ticketId}`);
}

export async function assignUser(
  ticketId: string,
  userId: string
): Promise<AssignmentResponse> {
  const { data } = await apiClient.post<AssignmentResponse>(
    `/tickets/${ticketId}/assignments`,
    { user_id: userId }
  );
  return data;
}

export async function unassignUser(
  ticketId: string,
  userId: string
): Promise<void> {
  await apiClient.delete(`/tickets/${ticketId}/assignments/${userId}`);
}

export async function listProgress(
  ticketId: string
): Promise<ProgressListResponse> {
  const { data } = await apiClient.get<ProgressListResponse>(
    `/tickets/${ticketId}/progress`
  );
  return data;
}

export async function submitProgress(
  ticketId: string,
  content: string
): Promise<ProgressUpdateResponse> {
  const { data } = await apiClient.put<ProgressUpdateResponse>(
    `/tickets/${ticketId}/progress`,
    { content }
  );
  return data;
}

export async function transitionTicket(
  ticketId: string,
  toStatus: TicketStatus
): Promise<TicketResponse | TransitionBlockedError> {
  try {
    const { data } = await apiClient.post<TicketResponse>(
      `/tickets/${ticketId}/transitions`,
      { to_status: toStatus }
    );
    return data;
  } catch (error: unknown) {
    if (
      typeof error === "object" &&
      error !== null &&
      "response" in error
    ) {
      const axiosError = error as { response: { status: number; data: TransitionBlockedError } };
      if (axiosError.response.status === 422) {
        return axiosError.response.data;
      }
    }
    throw error;
  }
}

export async function listTicketEvents(
  ticketId: string,
  params?: { page?: number; page_size?: number }
): Promise<EventListResponse> {
  const { data } = await apiClient.get<EventListResponse>(
    `/tickets/${ticketId}/events`,
    { params }
  );
  return data;
}

export async function searchTags(q: string): Promise<TagResponse[]> {
  const { data } = await apiClient.get<TagResponse[]>("/tags", { params: { q } });
  return data;
}

export async function addTag(ticketId: string, name: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${ticketId}/tags`, { name });
  return data;
}

export async function removeTag(ticketId: string, name: string): Promise<TicketResponse> {
  const { data } = await apiClient.delete<TicketResponse>(
    `/tickets/${ticketId}/tags/${encodeURIComponent(name)}`
  );
  return data;
}
