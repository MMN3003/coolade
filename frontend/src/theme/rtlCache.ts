import createCache from '@emotion/cache';
import rtlPlugin from 'stylis-plugin-rtl';
import { prefixer } from 'stylis';

/**
 * Emotion cache with the RTL stylis plugin, per TECH.md §9:
 * "ThemeProvider با direction:'rtl' + CacheProvider (emotion) + stylis-plugin-rtl"
 */
export const rtlCache = createCache({
  key: 'muirtl',
  stylisPlugins: [prefixer, rtlPlugin],
});
