import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import fa from './fa.json';
import en from './en.json';

/**
 * i18n structure per TECH.md §9: UI is Persian-first, RTL. English resources
 * are only partially filled in for now (top-level nav/auth/common) — full
 * English strings are a P3 item per docs/PRD.md §9. `fallbackLng: 'fa'` means
 * any key missing from `en` gracefully falls back to Persian rather than
 * breaking, so the language switch is safe to ship incrementally.
 */
void i18n.use(initReactI18next).init({
  resources: {
    fa: { translation: fa },
    en: { translation: en },
  },
  lng: 'fa',
  fallbackLng: 'fa',
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
