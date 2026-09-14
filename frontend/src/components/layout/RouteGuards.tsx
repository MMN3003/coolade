import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import LoadingState from '@/components/common/LoadingState';
import type { FeatureKey } from '@/api/types';

export function RequireAuth() {
  const status = useAuthStore((s) => s.status);
  const location = useLocation();

  if (status === 'idle' || status === 'loading') return <LoadingState />;
  if (status === 'anonymous') {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <Outlet />;
}

/** Plan-gated area: any of `features` must be in the user's plan, else back to chat. */
export function RequireFeature({ features }: { features: FeatureKey[] }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <LoadingState />;
  if (!features.some((f) => user.features.includes(f))) return <Navigate to="/chat" replace />;
  return <Outlet />;
}

export function RequireAdmin() {
  const user = useAuthStore((s) => s.user);
  if (!user) return <LoadingState />;
  if (user.role !== 'admin') return <Navigate to="/chat" replace />;
  return <Outlet />;
}
