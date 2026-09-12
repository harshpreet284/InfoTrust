import type { ReactNode } from "react";

interface FormContainerProps {
  title: string;
  description: string;
  children: ReactNode;
}

export function FormContainer({ title, description, children }: FormContainerProps) {
  return (
    <div className="w-full max-w-md mx-auto sm:bg-white sm:rounded-2xl sm:shadow-sm sm:border sm:border-slate-100 sm:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        <p className="mt-2 text-sm text-slate-600">{description}</p>
      </div>
      {children}
    </div>
  );
}
