import { apiClient } from "./client";
import type { ProjectGroup } from "../types";

export interface ProjectGroupCreate {
  identifier: string;
  name: string;
  description?: string;
}

export interface ProjectGroupUpdate {
  name?: string;
  description?: string;
}

export interface ProjectGroupListResponse {
  items: ProjectGroup[];
  total: number;
}

export async function listGroups(): Promise<ProjectGroup[]> {
  const { data } = await apiClient.get<ProjectGroupListResponse>("/groups");
  return data.items;
}

export async function createGroup(body: ProjectGroupCreate): Promise<ProjectGroup> {
  const { data } = await apiClient.post<ProjectGroup>("/groups", body);
  return data;
}

export async function updateGroup(id: string, body: ProjectGroupUpdate): Promise<ProjectGroup> {
  const { data } = await apiClient.patch<ProjectGroup>(`/groups/${id}`, body);
  return data;
}

export async function deleteGroup(id: string): Promise<void> {
  await apiClient.delete(`/groups/${id}`);
}
