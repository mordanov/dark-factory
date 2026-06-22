import { apiClient } from "./client";
import type { UserSummary } from "../types";

export async function listUsers(): Promise<UserSummary[]> {
  const { data } = await apiClient.get<UserSummary[]>("/users");
  return data;
}
