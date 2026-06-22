import { create } from "zustand";
import type { UserSummary } from "../types";

const RT_KEY = "rt";

interface AuthState {
  accessToken: string | null;
  currentUser: UserSummary | null;
  refreshToken: string | null;
  // true while we're attempting to exchange a stored refresh token for a new access token
  isRestoring: boolean;
  login: (accessToken: string, refreshToken: string | undefined, user: UserSummary) => void;
  setAccessToken: (token: string) => void;
  setRestored: () => void;
  logout: () => void;
}

const storedRefreshToken = sessionStorage.getItem(RT_KEY);

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  currentUser: null,
  refreshToken: storedRefreshToken,
  isRestoring: storedRefreshToken !== null,

  login(accessToken, refreshToken, user) {
    if (refreshToken) {
      sessionStorage.setItem(RT_KEY, refreshToken);
    }
    set({ accessToken, refreshToken: refreshToken ?? null, currentUser: user, isRestoring: false });
  },

  setAccessToken(token) {
    set({ accessToken: token });
  },

  setRestored() {
    set({ isRestoring: false });
  },

  logout() {
    sessionStorage.removeItem(RT_KEY);
    set({ accessToken: null, refreshToken: null, currentUser: null, isRestoring: false });
  },
}));
