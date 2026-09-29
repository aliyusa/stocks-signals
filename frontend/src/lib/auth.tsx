import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { User } from "./types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api<User>("/api/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          // access cookie may have expired; the refresh cookie can renew it
          try {
            return await api<User>("/api/auth/refresh", { method: "POST" });
          } catch {
            return null;
          }
        }
        throw e;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });

  const value: AuthCtx = {
    user: me.data ?? null,
    loading: me.isLoading,
    login: async (email, password) => {
      const u = await api<User>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      qc.setQueryData(["me"], u);
    },
    register: async (email, password, full_name) => {
      const u = await api<User>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: full_name || null }),
      });
      qc.setQueryData(["me"], u);
    },
    logout: async () => {
      try {
        await api("/api/auth/logout", { method: "POST" });
      } finally {
        // Keep the "me" observer alive (so the UI re-renders) and drop every other cached response.
        qc.setQueryData(["me"], null);
        qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      }
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
