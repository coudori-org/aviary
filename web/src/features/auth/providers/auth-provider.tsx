"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { User } from "@/types";
import { ensureValidToken, initiateLogin, isAuthenticated, logout as doLogout } from "@/lib/auth";
import { http } from "@/lib/http";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  user: User | null;
  status: AuthStatus;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * AuthProvider — single source of truth for the current user.
 *
 * Status state machine:
 *   loading → authenticated   (token present + /auth/me succeeded)
 *   loading → unauthenticated (no token, refresh failed, or /auth/me threw)
 *
 * Components should switch on `status` rather than `user == null` to
 * distinguish "not logged in" from "still loading".
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const refreshUser = useCallback(async () => {
    if (!isAuthenticated()) {
      setUser(null);
      setStatus("unauthenticated");
      return;
    }

    const token = await ensureValidToken();
    if (!token) {
      setUser(null);
      setStatus("unauthenticated");
      return;
    }

    try {
      const u = await http.get<User>("/auth/me");
      setUser(u);
      setStatus("authenticated");
    } catch {
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const handleLogin = useCallback(async () => {
    await initiateLogin();
  }, []);

  const handleLogout = useCallback(async () => {
    setUser(null);
    setStatus("unauthenticated");
    await doLogout();
  }, []);

  return (
    <AuthContext.Provider value={{ user, status, login: handleLogin, logout: handleLogout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
