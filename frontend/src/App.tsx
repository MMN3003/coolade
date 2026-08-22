import { lazy, Suspense, useEffect } from 'react';
import { Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom';
import { setUnauthorizedHandler } from '@/api/client';
import { useAuthStore } from '@/store/authStore';
import { useSession } from '@/hooks/useSession';
import AppShell from '@/components/layout/AppShell';
import { RequireAdmin, RequireAuth } from '@/components/layout/RouteGuards';
import LoadingState from '@/components/common/LoadingState';

// Route-level code splitting: login/shell load eagerly, everything behind
// auth (esp. the markdown/highlight-heavy chat page and recharts-heavy usage
// pages) is lazy-loaded to keep the initial bundle small.
import LoginPage from '@/pages/LoginPage';
const ChatPage = lazy(() => import('@/pages/ChatPage'));
const UsagePage = lazy(() => import('@/pages/UsagePage'));
const KeysPage = lazy(() => import('@/pages/KeysPage'));
const HelpPage = lazy(() => import('@/pages/HelpPage'));
const AdminUsersPage = lazy(() => import('@/pages/admin/AdminUsersPage'));
const AdminPoliciesPage = lazy(() => import('@/pages/admin/AdminPoliciesPage'));
const AdminUsagePage = lazy(() => import('@/pages/admin/AdminUsagePage'));
const AdminModelsPage = lazy(() => import('@/pages/admin/AdminModelsPage'));
const AdminSettingsPage = lazy(() => import('@/pages/admin/AdminSettingsPage'));
const AdminAuditPage = lazy(() => import('@/pages/admin/AdminAuditPage'));
import NotFoundPage from '@/pages/NotFoundPage';

export default function App() {
  const navigate = useNavigate();
  const reset = useAuthStore((s) => s.reset);
  const status = useAuthStore((s) => s.status);
  const { isLoading } = useSession();

  useEffect(() => {
    setUnauthorizedHandler(() => {
      reset();
      navigate('/login', { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate, reset]);

  if (status === 'idle' && isLoading) return <LoadingState />;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route
            element={
              <Suspense fallback={<LoadingState />}>
                <Outlet />
              </Suspense>
            }
          >
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:conversationId" element={<ChatPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="/keys" element={<KeysPage />} />
            <Route path="/help" element={<HelpPage />} />

            <Route element={<RequireAdmin />}>
              <Route path="/admin/users" element={<AdminUsersPage />} />
              <Route path="/admin/policies" element={<AdminPoliciesPage />} />
              <Route path="/admin/usage" element={<AdminUsagePage />} />
              <Route path="/admin/models" element={<AdminModelsPage />} />
              <Route path="/admin/settings" element={<AdminSettingsPage />} />
              <Route path="/admin/audit" element={<AdminAuditPage />} />
            </Route>

            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
