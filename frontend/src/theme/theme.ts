import { createTheme } from '@mui/material/styles';
import { faIR } from '@mui/material/locale';

/**
 * App theme: RTL direction, Vazirmatn as the primary typeface (self-hosted via
 * @fontsource/vazirmatn — imported once in main.tsx, no CDN per TECH.md §9).
 */
export const theme = createTheme(
  {
    direction: 'rtl',
    palette: {
      mode: 'light',
      primary: { main: '#2e7d32' },
      secondary: { main: '#0277bd' },
      background: { default: '#f5f7f6' },
    },
    typography: {
      fontFamily: [
        'Vazirmatn',
        'Roboto',
        'Arial',
        'sans-serif',
      ].join(','),
    },
    shape: { borderRadius: 10 },
    components: {
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: { root: { borderRadius: 8 } },
      },
      MuiPaper: {
        styleOverrides: { root: { backgroundImage: 'none' } },
      },
    },
  },
  faIR
);
