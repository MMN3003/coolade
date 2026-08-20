/**
 * Persian (Jalali) date formatting via Intl — no extra date library needed.
 * TECH.md §9 asks for Persian date display; `Intl.DateTimeFormat` with
 * `calendar: 'persian'` + `locale: 'fa-IR'` covers this natively.
 */

const dateFormatter = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
});

const dateTimeFormatter = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const shortDateFormatter = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
  month: 'short',
  day: 'numeric',
});

export function formatPersianDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return dateFormatter.format(d);
}

export function formatPersianDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return dateTimeFormatter.format(d);
}

export function formatPersianShortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return shortDateFormatter.format(d);
}

export function formatCredits(value: number | null | undefined): string {
  if (value === null || value === undefined) return '۰';
  return new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(value);
}
