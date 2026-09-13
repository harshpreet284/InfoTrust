import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { AuthLayout } from './components/auth/AuthLayout';
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { RoleGuard } from './components/auth/RoleGuard';
import { DashboardPage } from './pages/dashboard/DashboardPage';
import { SubmitClaimPage } from './pages/claims/SubmitClaimPage';
import { HistoryPage } from './pages/history/HistoryPage';
import { ProfilePage } from './pages/profile/ProfilePage';
import { SettingsPage } from './pages/settings/SettingsPage';
import { AdminAreaPage } from './pages/admin/AdminAreaPage';

function AuthInterceptor({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();

  useEffect(() => {
    const handleUnauthorized = () => {
      navigate('/login', { replace: true });
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, [navigate]);

  return <>{children}</>;
}

function App() {
  return (
    <BrowserRouter>
      <AuthInterceptor>
        <Routes>
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/claims/submit" element={<SubmitClaimPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/settings" element={<SettingsPage />} />

          <Route element={<RoleGuard allowedRoles={['ADMIN']} />}>
            <Route path="/admin" element={<AdminAreaPage />} />
          </Route>
        </Route>

        {/* Fallback route - redirect to dashboard */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </AuthInterceptor>
    </BrowserRouter>
  );
}

export default App;
