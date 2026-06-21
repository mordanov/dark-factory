import { apiClient } from "./client";
import type { TokenResponse } from "../types";

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/login", { email, password });
  return data;
}

export async function logout(refreshToken: string): Promise<void> {
  await apiClient.post("/auth/logout", { refresh_token: refreshToken });
}

export async function refresh(refreshToken: string): Promise<string> {
  const { data } = await apiClient.post<{ access_token: string }>("/auth/refresh", {
    refresh_token: refreshToken,
  });
  return data.access_token;
}
