import { useState } from "react";
import { useAuth } from "./AuthProvider";
import { LoadingIndicator } from "../ui/LoadingIndicator";

export function LogoutButton() {
  const { logout } = useAuth();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLogout = () => {
    setIsLoggingOut(true);
    logout();
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
