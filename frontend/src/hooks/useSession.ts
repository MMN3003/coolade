import { useQuery } from '@tanstack/react-query';
import { authApi } from '@/api/endpoints';
import { ApiError } from '@/api/client';
import { useAuthStore } from '@/store/authStore';
import { useEffect } from 'react';

/**
 * Bootstraps the current session by calling GET /api/auth/me (TECH.md §8).
 * A 401 here just means "not logged in" — not an app error — so we swallow it
 * and let route guards redirect to /login.
 */
export function useSession() {
  const setUser = useAuthStore((s) => s.setUser);
  const setStatus = useAuthStore((s) => s.setStatus);

  const query = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authApi.me,
    retry: false,
  });

  useEffect(() => {
    if (query.isSuccess) {
      setUser(query.data);
    } else if (query.isError) {
      const err = query.error;
      if (err instanceof ApiError && err.status === 401) {
        setUser(null);
      } else {
        // non-auth error (network/server) — still treat as anonymous for guards,
        // the page-level error boundary/toast can surface details separately.
        setUser(null);
      }
    }
  }, [query.isSuccess, query.isError, query.data, query.error, setUser]);

  useEffect(() => {
    if (query.isLoading) setStatus('loading');
  }, [query.isLoading, setStatus]);

  return query;
}
