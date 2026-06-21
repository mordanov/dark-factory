import { apiClient } from "./client";
import type { AdminUserResponse, AdminUserCreate, AdminUserUpdate, AdminUserListResponse } from "../types";

export async function listAdminUsers(): Promise<AdminUserListResponse> {
  const { data } = await apiClient.get<AdminUserListResponse>("/admin/users");
  return data;
}

export async function createAdminUser(payload: AdminUserCreate): Promise<AdminUserResponse> {
  const { data } = await apiClient.post<AdminUserResponse>("/admin/users", payload);
  return data;
}

export async function updateAdminUser(userId: string, payload: AdminUserUpdate): Promise<AdminUserResponse> {
  const { data } = await apiClient.patch<AdminUserResponse>(`/admin/users/${userId}`, payload);
  return data;
}

export async function blockAdminUser(userId: string): Promise<AdminUserResponse> {
  const { data } = await apiClient.post<AdminUserResponse>(`/admin/users/${userId}/block`);
  return data;
}

export async function unblockAdminUser(userId: string): Promise<AdminUserResponse> {
  const { data } = await apiClient.post<AdminUserResponse>(`/admin/users/${userId}/unblock`);
  return data;
}
