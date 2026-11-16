import i18n from './i18n';

/**
 * Runtime product branding. The name comes from the backend's APP_NAME setting
 * (GET /api/branding), so one build can be deployed under any product name.
 * Defaults keep the UI usable if the call fails.
 */
export const branding = {
  name: 'Coolade',
  slug: 'coolade',
  apiKeyPrefix: 'coolade_live_',
};

function applyToDocument(): void {
  document.title = `${branding.name} Gateway`;
  const vars = { appName: branding.name, keyPrefix: branding.apiKeyPrefix };
  i18n.options.interpolation = { ...(i18n.options.interpolation ?? {}), defaultVariables: vars };
}

/** Replace {{appName}} / {{keyPrefix}} placeholders in bundled markdown content. */
export function applyBranding(text: string): string {
  return text.split('{{appName}}').join(branding.name).split('{{keyPrefix}}').join(branding.apiKeyPrefix);
}

export async function loadBranding(): Promise<void> {
  applyToDocument();
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), 3000);
  try {
    const res = await fetch('/api/branding', { signal: ctrl.signal, credentials: 'same-origin' });
    if (res.ok) {
      const data = (await res.json()) as { name?: string; slug?: string; api_key_prefix?: string };
      if (data.name) branding.name = data.name;
      if (data.slug) branding.slug = data.slug;
      if (data.api_key_prefix) branding.apiKeyPrefix = data.api_key_prefix;
    }
  } catch {
    // keep defaults
  } finally {
    window.clearTimeout(timer);
    applyToDocument();
  }
}
