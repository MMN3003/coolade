import { create } from 'zustand';
import type { MeResponse } from '@/api/types';

interface AuthState {
  user: MeResponse | null;
  status: 'idle' | 'loading' | 'authenticated' | 'anonymous';
  setUser: (user: MeResponse | null) => void;
  setStatus: (status: AuthState['status']) => void;
  reset: () => void;
}

/**
 * Session/user state. The session itself lives server-side in an HttpOnly
 * cookie (TECH.md §7.1) — this store just caches what `/api/auth/me` told us
 * so the app shell, route guards, and quota banner don't re-fetch constantly.
 */
export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: 'idle',
  setUser: (user) => set({ user, status: user ? 'authenticated' : 'anonymous' }),
  setStatus: (status) => set({ status }),
  reset: () => set({ user: null, status: 'anonymous' }),
}));
