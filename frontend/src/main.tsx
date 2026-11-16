import React, { useMemo } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { CacheProvider } from '@emotion/react';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Vazirmatn self-hosted (no CDN) — TECH.md §9.
import '@fontsource/vazirmatn/400.css';
import '@fontsource/vazirmatn/500.css';
import '@fontsource/vazirmatn/600.css';
import '@fontsource/vazirmatn/700.css';
// Code block syntax highlighting theme (rehype-highlight relies on highlight.js CSS classes).
import 'highlight.js/styles/github-dark.css';

import './i18n';
import { loadBranding } from './branding';
import { rtlCache } from './theme/rtlCache';
import { makeTheme } from './theme/theme';
import { useUiStore } from './store/uiStore';
import App from './App';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

/**
 * Root wrapper: rebuilds the MUI theme whenever the persisted theme mode
 * changes (uiStore, localStorage key `coolade.theme`). The RTL emotion cache is
 * mode-independent, so it stays fixed while only the ThemeProvider swaps.
 */
function Root() {
  const themeMode = useUiStore((s) => s.themeMode);
  const activeTheme = useMemo(() => makeTheme(themeMode), [themeMode]);

  return (
    <CacheProvider value={rtlCache}>
      <ThemeProvider theme={activeTheme}>
        <CssBaseline />
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </ThemeProvider>
    </CacheProvider>
  );
}

void loadBranding().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <Root />
    </React.StrictMode>
  );
});
