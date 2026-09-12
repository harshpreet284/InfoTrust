import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";

import { FormContainer } from "../../components/ui/FormContainer";
import { ValidationMessage } from "../../components/ui/ValidationMessage";
import { LoadingIndicator } from "../../components/ui/LoadingIndicator";
import { RegistrationSchema } from "../../schemas/auth.schema";
import type { RegistrationFormValues } from "../../schemas/auth.schema";
import { authService } from "../../services/auth.service";

export function RegisterPage() {
  const navigate = useNavigate();
  const [rootError, setRootError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegistrationFormValues>({
    resolver: zodResolver(RegistrationSchema),
  });

  const onSubmit = async (data: RegistrationFormValues) => {
    setRootError(null);
    try {
      await authService.register(data);
      // Success: Navigate to login with success state
      navigate("/login", {
        state: { message: "Registration successful. Please log in." },
      });
    } catch (error) {
      if (isAxiosError(error) && error.response) {
        const { status, data: errorData } = error.response;

        // 409 Conflict - e.g., duplicate email
        if (status === 409 && errorData.errors) {
          Object.entries(errorData.errors).forEach(([field, messages]) => {
            setError(field as keyof RegistrationFormValues, {
              type: "server",
              message: (messages as string[])[0]
            });
          });
          return;
        }

        // 422 Validation Error - Django Ninja native format
        if (status === 422 && Array.isArray(errorData.detail)) {
          errorData.detail.forEach((err: any) => {
            const field = err.loc?.[err.loc.length - 1];
            if (field && ["full_name", "email", "password", "confirm_password"].includes(field)) {
              setError(field as keyof RegistrationFormValues, {
                type: "server",
                message: err.msg
              });
            } else {
              // Unmappable validation error
              setRootError(err.msg || "A validation error occurred.");
            }
          });
          return;
        }
      }

      // Generic fallback error
      setRootError("An unexpected error occurred. Please try again.");
    }
  };

  return (
    <FormContainer
      title="Create an account"
      description="Join InfoTrust to start analyzing claims."
    >
      <form className="space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>

        {rootError && (
          <div className="bg-red-50 text-red-700 p-3 rounded-lg text-sm font-medium mb-4">
            {rootError}
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1" htmlFor="full_name">
            Full Name
          </label>
          <input
            id="full_name"
            type="text"
            placeholder="Jane Doe"
            autoComplete="name"
            className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:outline-none transition-shadow ${
              errors.full_name
                ? "border-red-300 focus:ring-red-500 focus:border-red-500"
                : "border-slate-300 focus:ring-primary-500 focus:border-primary-500"
            }`}
            disabled={isSubmitting}
            {...register("full_name")}
          />
          <ValidationMessage message={errors.full_name?.message} />
        </div>

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
            autoComplete="new-password"
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

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1" htmlFor="confirm_password">
            Confirm Password
          </label>
          <input
            id="confirm_password"
            type="password"
            placeholder="••••••••"
            autoComplete="new-password"
            className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:outline-none transition-shadow ${
              errors.confirm_password
                ? "border-red-300 focus:ring-red-500 focus:border-red-500"
                : "border-slate-300 focus:ring-primary-500 focus:border-primary-500"
            }`}
            disabled={isSubmitting}
            {...register("confirm_password")}
          />
          <ValidationMessage message={errors.confirm_password?.message} />
        </div>

        <button
          type="submit"
          className="w-full flex justify-center items-center py-2.5 px-4 mt-2 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <>
              <LoadingIndicator className="w-4 h-4 mr-2" />
              Creating account...
            </>
          ) : (
            "Create account"
          )}
        </button>

        <p className="text-center text-sm text-slate-600 mt-6">
          Already have an account?{" "}
          <a href="/login" className="font-medium text-primary-600 hover:text-primary-500">
            Sign in
          </a>
        </p>
      </form>
    </FormContainer>
  );
}
