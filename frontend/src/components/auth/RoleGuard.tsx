import { useEffect, useState } from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { authService } from '../../services/auth.service';
import { tokenStorage } from '../../lib/token-storage';
import { LoadingIndicator } from '../ui/LoadingIndicator';

interface RoleGuardProps {
  allowedRoles: string[];
}

export function RoleGuard({ allowedRoles }: RoleGuardProps) {
  const [role, setRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const fetchRole = async () => {
      const token = tokenStorage.getAccessToken();
      if (!token) {
        if (isMounted) {
          setLoading(false);
          setError(true);
        }
        return;
      }
      
      try {
        const response = await authService.getCurrentUser();
        if (isMounted) {
          setRole(response.data?.role || null);
        }
      } catch (e) {
        if (isMounted) {
          setError(true);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchRole();

    return () => {
      isMounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <LoadingIndicator className="w-8 h-8 text-primary-600" />
      </div>
    );
  }

  if (error || !role || !allowedRoles.includes(role)) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
