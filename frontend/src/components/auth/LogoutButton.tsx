import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { tokenStorage } from "../../lib/token-storage";
import { authService } from "../../services/auth.service";
import { LoadingIndicator } from "../ui/LoadingIndicator";

export function LogoutButton() {
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    const refreshToken = tokenStorage.getRefreshToken();
    
    if (refreshToken) {
      try {
        await authService.logout(refreshToken);
      } catch (error) {
        // Log out locally even if the server request fails
        console.warn("Server logout failed or token invalid.", error);
      }
    }
    
    tokenStorage.clearTokens();
    navigate("/login", { replace: true });
  };

  return (
    <button
      onClick={handleLogout}
      disabled={isLoggingOut}
      className="inline-flex items-center px-4 py-2 border border-slate-300 rounded-md shadow-sm text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
    >
      {isLoggingOut ? (
        <>
          <LoadingIndicator className="w-4 h-4 mr-2" />
          Signing out...
        </>
      ) : (
        "Sign out"
      )}
    </button>
  );
}
