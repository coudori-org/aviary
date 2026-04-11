"use client";

import { useCallback, useState } from "react";
import { http } from "@/lib/http";
import { useAuth } from "@/features/auth/providers/auth-provider";
import type { User, UserPreferences } from "@/types";

interface UsePreferencesResult {
  preferences: UserPreferences;
  updatePreferences: (patch: UserPreferences) => Promise<void>;
}

/**
 * usePreferences — read + update the current user's preferences blob.
 *
 * Optimistic overlay is layered over the auth user's prefs. On server
 * failure the overlay is rolled back and the error is rethrown so the
 * caller can react.
 */
export function usePreferences(): UsePreferencesResult {
  const { user, refreshUser } = useAuth();
  const [overlay, setOverlay] = useState<UserPreferences>({});

  const preferences: UserPreferences = {
    ...(user?.preferences ?? {}),
    ...overlay,
  };

  const updatePreferences = useCallback(
    async (patch: UserPreferences) => {
      const patchKeys = Object.keys(patch) as (keyof UserPreferences)[];
      setOverlay((prev) => ({ ...prev, ...patch }));
      try {
        await http.patch<User>("/auth/me/preferences", { preferences: patch });
        await refreshUser();
      } catch (err) {
        setOverlay((prev) => {
          const next = { ...prev };
          for (const key of patchKeys) delete next[key];
          return next;
        });
        throw err;
      }
    },
    [refreshUser],
  );

  return { preferences, updatePreferences };
}
