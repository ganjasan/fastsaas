/**
 * Zustand auth store — in-memory access token + current actor.
 *
 * Per ADR-008 hybrid storage: the access token NEVER touches localStorage or
 * sessionStorage. Refresh tokens live in an httpOnly cookie set by the backend.
 *
 * Re-exports the legacy `tokenStore` API so existing modules (api/client.ts)
 * keep working without a sweeping rename.
 */
import { create } from "zustand";

import type { CurrentActor } from "@/api/generated/fastSaaS.schemas";

interface AuthState {
  accessToken: string | null;
  currentActor: CurrentActor | null;
  setSession: (token: string, actor: CurrentActor) => void;
  setAccessToken: (token: string | null) => void;
  setCurrentActor: (actor: CurrentActor | null) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  currentActor: null,
  setSession: (token, actor) => set({ accessToken: token, currentActor: actor }),
  setAccessToken: (token) => set({ accessToken: token }),
  setCurrentActor: (actor) => set({ currentActor: actor }),
  clear: () => set({ accessToken: null, currentActor: null }),
}));

/** Imperative shim used by the orval mutator (no React context available there). */
export const tokenStore = {
  getAccessToken: (): string | null => useAuthStore.getState().accessToken,
  setAccessToken: (token: string | null): void => useAuthStore.getState().setAccessToken(token),
  clear: (): void => useAuthStore.getState().clear(),
};
