import Alert from '@mui/material/Alert';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/authStore';

/**
 * Quota warning banner per TECH.md §9: yellow at >=80% used, red once the
 * period budget is fully exhausted. Reads the cached quota summary from
 * /api/auth/me (refreshed whenever the app shell remounts / react-query
 * refetches) — good enough given F6.3's "up to 1 minute lag" allowance.
 */
export default function QuotaBanner() {
  const { t } = useTranslation();
  const quota = useAuthStore((s) => s.user?.quota);
  if (!quota) return null;

  const budget = quota.limit_credits + quota.bonus_credits;
  if (budget <= 0) return null;
  const ratio = quota.used_credits / budget;
  if (ratio < 0.8) return null;

  const exceeded = quota.used_credits >= budget;

  return (
    <Alert severity={exceeded ? 'error' : 'warning'} sx={{ borderRadius: 0 }}>
      {exceeded
        ? t('nav.quotaBannerExceeded')
        : t('nav.quotaBannerWarning', { percent: Math.floor(ratio * 100) })}
    </Alert>
  );
}
