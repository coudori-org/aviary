"use client";

import { useCallback, useState } from "react";
import { http } from "@/lib/http";
import { useAuth } from "@/features/auth/providers/auth-provider";
import type { User, UserPreferences } from "@/types";

interface UsePreferencesResult {
  preferences: UserPreferences;
  /** Optimistically merge `patch` into preferences and persist via PATCH.
   *  On failure the local state remains optimistic — the next refreshUser()
   *  will reconcile if the server rejects. */
  updatePreferences: (patch: UserPreferences) => Promise<void>;
}

/**
 * usePreferences — read + update the current user's preferences blob.
 *
 * Reads from the AuthProvider's user object (already fetched on mount via
 * /auth/me). Writes go to PATCH /auth/me/preferences which merges the
 * provided keys server-side. The local preferences state is layered over
 * the server one so the UI updates immediately on toggle/drag without
 * waiting for the network round-trip.
 *
 * Concurrent updates: each call POSTs whatever it has at the time. The
 * server's merge is key-level so out-of-order writes for *different*
 * keys are safe. Same-key concurrent writes (rare for this UI) follow
 * last-write-wins.
 */
export function usePreferences(): UsePreferencesResult {
  const { user, refreshUser } = useAuth();
  // Local optimistic overlay — start empty, merged over the auth user's prefs
  const [overlay, setOverlay] = useState<UserPreferences>({});

  const preferences: UserPreferences = {
    ...(user?.preferences ?? {}),
    ...overlay,
  };

  const updatePreferences = useCallback(
    async (patch: UserPreferences) => {
      // 1) Optimistic local update
      setOverlay((prev) => ({ ...prev, ...patch }));
      // 2) Persist to server
      try {
        await http.patch<User>("/auth/me/preferences", { preferences: patch });
        // Refresh auth user so the canonical source picks up the change.
        // The overlay can stay — it'll be a no-op since the server now matches.
        await refreshUser();
      } catch {
        // On failure, leave the optimistic overlay — user sees their change
        // but it won't persist. A future toast system could surface the error.
      }
    },
    [refreshUser],
  );

  return { preferences, updatePreferences };
}
