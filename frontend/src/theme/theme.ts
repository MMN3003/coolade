import { createTheme, type Theme } from '@mui/material/styles';
import { faIR } from '@mui/material/locale';

/**
 * App theme: RTL direction, Vazirmatn as the primary typeface (self-hosted via
 * @fontsource/vazirmatn — imported once in main.tsx, no CDN per TECH.md §9).
 *
 * Two cohesive palettes are supported through `makeTheme(mode)`:
 *  - `dark`  — the original ChatGPT/GapGPT-inspired look: near-black canvas,
 *              #1e1e1e surfaces, soft 1px dividers, a single cool-blue accent.
 *  - `light` — a clean ChatGPT-light look: near-white canvas, #f7f7f8 surfaces,
 *              dark text, subtle #e5e5e5 borders, the same cool-blue accent.
 *
 * The active mode is chosen at runtime (see uiStore + main.tsx). Global
 * component overrides derive their colours from the mode tokens below so they
 * read correctly in BOTH modes — nothing dark is hardcoded into an override.
 */

export type ThemeMode = 'light' | 'dark';

/**
 * Neutral elevated surface used for user bubbles / hover rails. Exposed as a
 * CSS custom property (set per-mode via the MuiCssBaseline override below) so
 * the value follows the active theme without touching consumers. The literal
 * fallback keeps the original dark bubble if the variable is ever unresolved.
 */
export const SURFACE_2 = 'var(--ec-surface-2, #2b2b2b)';

// Shared cool-blue accent (Coolade brand) — identical in both modes.
const ACCENT = { main: '#1488c8', light: '#3aa0d8', dark: '#0f6fa3', contrastText: '#ffffff' };

const tokens = {
  dark: {
    secondary: '#2bb5a8',
    background: { default: '#0d0d0d', paper: '#1e1e1e' },
    text: { primary: '#ECECEC', secondary: '#9a9a9a' },
    divider: '#2a2a2a',
    action: { hover: 'rgba(255,255,255,0.06)', selected: 'rgba(255,255,255,0.10)', active: '#c7c7c7' },
    error: '#f16063',
    warning: '#e0a642',
    surface2: '#2b2b2b',
    outline: '#2f2f2f',
    selectedBg: 'rgba(255,255,255,0.08)',
    selectedHover: 'rgba(255,255,255,0.12)',
    scrollThumb: 'rgba(255,255,255,0.16)',
    scrollThumbHover: 'rgba(255,255,255,0.30)',
  },
  light: {
    secondary: '#1f8f85',
    background: { default: '#ffffff', paper: '#f7f7f8' },
    text: { primary: '#1a1a1a', secondary: '#5a5a5a' },
    divider: '#e5e5e5',
    action: { hover: 'rgba(0,0,0,0.04)', selected: 'rgba(0,0,0,0.08)', active: '#3a3a3a' },
    error: '#d32f2f',
    warning: '#b26a00',
    surface2: '#ececed',
    outline: '#dcdcdc',
    selectedBg: 'rgba(0,0,0,0.06)',
    selectedHover: 'rgba(0,0,0,0.10)',
    scrollThumb: 'rgba(0,0,0,0.18)',
    scrollThumbHover: 'rgba(0,0,0,0.34)',
  },
} as const;

export function makeTheme(mode: ThemeMode): Theme {
  const c = tokens[mode];
  return createTheme(
    {
      direction: 'rtl',
      palette: {
        mode,
        primary: ACCENT,
        secondary: { main: c.secondary },
        background: c.background,
        text: c.text,
        divider: c.divider,
        action: c.action,
        error: { main: c.error },
        warning: { main: c.warning },
        success: { main: ACCENT.main },
      },
      typography: {
        fontFamily: ['Vazirmatn', 'Roboto', 'Arial', 'sans-serif'].join(','),
      },
      shape: { borderRadius: 12 },
      components: {
        MuiCssBaseline: {
          styleOverrides: {
            ':root': {
              '--ec-surface-2': c.surface2,
            },
            // Thin, rounded, theme-tinted scrollbars everywhere (chat list,
            // sidebar, code blocks, dialogs) instead of the chunky OS default.
            // Firefox uses the standard properties; Chromium/Safari the
            // ::-webkit-scrollbar pseudo-elements. The thumb is inset with a
            // transparent border so it reads as a slim pill on a clear track.
            '*': {
              scrollbarWidth: 'thin',
              scrollbarColor: `${c.scrollThumb} transparent`,
            },
            '*::-webkit-scrollbar': {
              width: 10,
              height: 10,
            },
            '*::-webkit-scrollbar-track': {
              background: 'transparent',
            },
            '*::-webkit-scrollbar-thumb': {
              backgroundColor: c.scrollThumb,
              borderRadius: 999,
              border: '3px solid transparent',
              backgroundClip: 'content-box',
              minHeight: 32,
            },
            '*::-webkit-scrollbar-thumb:hover': {
              backgroundColor: c.scrollThumbHover,
            },
            '*::-webkit-scrollbar-corner': {
              background: 'transparent',
            },
          },
        },
        MuiButton: {
          defaultProps: { disableElevation: true },
          styleOverrides: { root: { borderRadius: 10, textTransform: 'none' } },
        },
        MuiPaper: {
          styleOverrides: { root: { backgroundImage: 'none' } },
        },
        MuiAppBar: {
          styleOverrides: { root: { backgroundImage: 'none' } },
        },
        MuiListItemButton: {
          styleOverrides: {
            root: {
              borderRadius: 8,
              '&.Mui-selected': {
                backgroundColor: c.selectedBg,
                '&:hover': { backgroundColor: c.selectedHover },
              },
            },
          },
        },
        MuiTooltip: {
          styleOverrides: {
            tooltip: { fontSize: '0.72rem' },
          },
        },
        MuiOutlinedInput: {
          styleOverrides: {
            notchedOutline: { borderColor: c.outline },
          },
        },
      },
    },
    faIR
  );
}

/**
 * Backwards-compatible default (dark) theme. Kept so any static importer keeps
 * working; the live app builds its theme dynamically from the persisted mode.
 */
export const theme = makeTheme('dark');
