// 作者：zcy
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { LoginResponse } from "../types";

interface AuthState {
  token: string | null;
  role: string | null;
  tenant: string | null;
  username: string | null;
  login: (resp: LoginResponse, username: string) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      tenant: null,
      username: null,
      login: (resp, username) =>
        set({
          token: resp.access_token,
          role: resp.role,
          tenant: resp.tenant,
          username,
        }),
      logout: () =>
        set({ token: null, role: null, tenant: null, username: null }),
    }),
    { name: "rentai-auth" },
  ),
);
