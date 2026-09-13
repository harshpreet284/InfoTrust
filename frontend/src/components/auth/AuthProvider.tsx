import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { authService } from '../../services/auth.service';
import type { UserOut } from '../../services/auth.service';
import { tokenStorage } from '../../lib/token-storage';

interface AuthContextType {
  currentUser: UserOut | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setAuthenticatedUser: (user: UserOut | null) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<UserOut | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  
  // isLoading remains true during the initial /me fetch if tokens exist on mount.
  const [isLoading, setIsLoading] = useState<boolean>(() => tokenStorage.hasTokens());
  
  const navigate = useNavigate();
  const location = useLocation();

  const setAuthenticatedUser = (user: UserOut | null) => {
    setCurrentUser(user);
    setIsAuthenticated(!!user);
    setIsLoading(false);
  };

  const logout = () => {
    // 1. Capture refresh token for best-effort backend revocation
    const refreshToken = tokenStorage.getRefreshToken();
    
    // 2. Immediately invalidate local session and advance generation
    tokenStorage.clearTokens();
    
    // 3. Take control of loading state and clear React auth state
    setCurrentUser(null);
    setIsAuthenticated(false);
    setIsLoading(false);
    
    // 4. Best-effort backend revocation (do not await or rely on success)
    if (refreshToken) {
      authService.logout(refreshToken).catch(err => {
        console.warn("Backend logout failed or token already invalid.", err);
      });
    }
    
    // 5. Navigate to login
    navigate('/login', { replace: true });
  };

  useEffect(() => {
    const handleUnauthorized = () => {
      setCurrentUser(null);
      setIsAuthenticated(false);
      setIsLoading(false);
      
      // Navigate only if not already on /login to prevent loops
      if (location.pathname !== '/login') {
        navigate('/login', { replace: true });
      }
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, [location.pathname, navigate]);

  useEffect(() => {
    // If no tokens exist on mount, we're already set to unauthenticated.
    if (!tokenStorage.hasTokens()) {
      return;
    }

    const startingGeneration = tokenStorage.getGeneration();
    
    const bootstrapSession = async () => {
      try {
        const response = await authService.getCurrentUser();
        
        // If generation still matches, apply the user
        if (tokenStorage.getGeneration() === startingGeneration) {
          setCurrentUser(response.data);
          setIsAuthenticated(true);
          setIsLoading(false);
        }
      } catch (error) {
        // If generation still matches, fail-closed gracefully (for non-401 errors).
        // If 401, Axios intercepts it, clears tokens, and fires auth:unauthorized.
        if (tokenStorage.getGeneration() === startingGeneration) {
          setCurrentUser(null);
          setIsAuthenticated(false);
          setIsLoading(false);
        }
      }
    };

    bootstrapSession();
  }, []); // Only runs on mount

  return (
    <AuthContext.Provider value={{ currentUser, isAuthenticated, isLoading, setAuthenticatedUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
