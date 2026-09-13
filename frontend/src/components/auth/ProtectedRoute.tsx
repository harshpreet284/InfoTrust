import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { tokenStorage } from '../../lib/token-storage';
import { LogoutButton } from './LogoutButton';

export function ProtectedRoute() {
  const location = useLocation();
  const token = tokenStorage.getAccessToken();

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="bg-white shadow-sm border-b border-slate-200 px-6 py-4 flex justify-between items-center">
        <div className="font-semibold text-slate-800 text-lg">InfoTrust</div>
        <LogoutButton />
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
