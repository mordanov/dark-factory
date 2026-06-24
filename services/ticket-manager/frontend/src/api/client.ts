import axios, { type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "../store/auth";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const header = await useAuthStore.getState().getAuthHeader();
  config.headers.Authorization = header.Authorization;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      await useAuthStore.getState().initialize();
    }
    return Promise.reject(error);
  }
);
