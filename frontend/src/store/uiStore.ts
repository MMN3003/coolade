import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ThemeMode } from '@/theme/theme';

interface UiState {
  themeMode: ThemeMode;
  toggleTheme: () => void;
  setThemeMode: (mode: ThemeMode) => void;
}

/**
 * Per-person UI preferences kept in the browser only (no backend). The theme
 * mode is persisted to localStorage under `coolade.theme` and rehydrated on
 * load, so each user keeps their light/dark choice on their own device. The
 * default is 'dark' — the app's original look.
 */
export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      themeMode: 'dark',
      toggleTheme: () =>
        set((s) => ({ themeMode: s.themeMode === 'dark' ? 'light' : 'dark' })),
      setThemeMode: (mode) => set({ themeMode: mode }),
    }),
    { name: 'coolade.theme' }
  )
);
