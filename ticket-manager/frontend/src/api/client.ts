import axios, { type AxiosRequestConfig, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "../store/auth";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let isRefreshing = false;
let pendingQueue: Array<{
  resolve: (value: string) => void;
  reject: (reason: unknown) => void;
}> = [];

function drainQueue(token: string | null, error: unknown) {
  pendingQueue.forEach(({ resolve, reject }) =>
    token ? resolve(token) : reject(error)
  );
  pendingQueue = [];
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config as AxiosRequestConfig & { _retry?: boolean };

    const url = original.url ?? "";
    const isAuthEndpoint = url.includes("/auth/login") || url.includes("/auth/refresh");
    if (error.response?.status !== 401 || original._retry || isAuthEndpoint) {
      return Promise.reject(error);
    }

    const { refreshToken, setAccessToken, logout } = useAuthStore.getState();

    if (!refreshToken) {
      logout();
      window.location.href = "/login";
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        pendingQueue.push({ resolve, reject });
      }).then((token) => {
        original.headers = { ...original.headers, Authorization: `Bearer ${token}` };
        return apiClient(original);
      });
    }

    original._retry = true;
    isRefreshing = true;

    try {
      const { data } = await axios.post<{ access_token: string }>(
        `${BASE_URL}/api/v1/auth/refresh`,
        { refresh_token: refreshToken }
      );
      setAccessToken(data.access_token);
      drainQueue(data.access_token, null);
      original.headers = {
        ...original.headers,
        Authorization: `Bearer ${data.access_token}`,
      };
      return apiClient(original);
    } catch (refreshError) {
      drainQueue(null, refreshError);
      logout();
      window.location.href = "/login";
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);
