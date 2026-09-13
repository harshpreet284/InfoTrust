import { useState } from "react";
import { useLocation, Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";

import { FormContainer } from "../../components/ui/FormContainer";
import { ValidationMessage } from "../../components/ui/ValidationMessage";
import { LoadingIndicator } from "../../components/ui/LoadingIndicator";
import { LoginSchema } from "../../schemas/auth.schema";
import type { LoginFormValues } from "../../schemas/auth.schema";
import { authService } from "../../services/auth.service";
import { tokenStorage } from "../../lib/token-storage";

export function LoginPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const successMessage = location.state?.message;

  const [rootError, setRootError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(LoginSchema),
  });

  const onSubmit = async (data: LoginFormValues) => {
    setRootError(null);
    try {
      const response = await authService.login(data);
      // Success: store tokens
      tokenStorage.setTokens(response.data.access_token, response.data.refresh_token);

      // Redirect to the originally requested URL or dashboard
      const from = location.state?.from?.pathname || "/";
      navigate(from, { replace: true });
    } catch (error) {
      if (isAxiosError(error) && error.response) {
        const { status, data: errorData } = error.response;

        // 401 or 403
        if ((status === 401 || status === 403) && errorData.message) {
          setRootError(errorData.message);
          return;
        }

        // 422 Validation Error - Django Ninja native format
        if (status === 422 && Array.isArray(errorData.detail)) {
          errorData.detail.forEach((err: any) => {
            const field = err.loc?.[err.loc.length - 1];
            if (field && ["email", "password"].includes(field)) {
              setError(field as keyof LoginFormValues, {
                type: "server",
                message: err.msg
              });
            } else {
              setRootError(err.msg || "A validation error occurred.");
            }
          });
          return;
        }
      }

      setRootError("An unexpected error occurred. Please try again.");
    }
  };


  return (
    <FormContainer 
      title="Welcome back" 
      description="Enter your credentials to access your account."
    >
      {successMessage && !rootError && (
        <div className="bg-green-50 text-green-700 p-3 rounded-lg text-sm font-medium mb-6">
          {successMessage}
        </div>
      )}

      {rootError && (
        <div className="bg-red-50 text-red-700 p-3 rounded-lg text-sm font-medium mb-6">
          {rootError}
        </div>
      )}

      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1" htmlFor="email">
            Email address
          </label>
          <input
            id="email"
            type="email"
            placeholder="name@example.com"
            autoComplete="email"
            className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:outline-none transition-shadow ${
              errors.email
                ? "border-red-300 focus:ring-red-500 focus:border-red-500"
                : "border-slate-300 focus:ring-primary-500 focus:border-primary-500"
            }`}
            disabled={isSubmitting}
            {...register("email")}
          />
          <ValidationMessage message={errors.email?.message} />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            placeholder="••••••••"
            autoComplete="current-password"
            className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:outline-none transition-shadow ${
              errors.password
                ? "border-red-300 focus:ring-red-500 focus:border-red-500"
                : "border-slate-300 focus:ring-primary-500 focus:border-primary-500"
            }`}
            disabled={isSubmitting}
            {...register("password")}
          />
          <ValidationMessage message={errors.password?.message} />
        </div>

        <button
          type="submit"
          className="w-full flex justify-center items-center py-2.5 px-4 mt-2 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <>
              <LoadingIndicator className="w-4 h-4 mr-2" />
              Signing in...
            </>
          ) : (
            "Sign in"
          )}
        </button>

        <p className="text-center text-sm text-slate-600 mt-6">
          Don't have an account?{" "}
          <Link to="/register" className="font-medium text-primary-600 hover:text-primary-500">
            Register now
          </Link>
        </p>
      </form>
    </FormContainer>
  );
}
