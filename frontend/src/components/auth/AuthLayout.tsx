import { Outlet } from "react-router-dom";
import { Logo } from "../ui/Logo";

export function AuthLayout() {
  return (
    <div className="min-h-screen flex w-full">
      {/* Branding Side - Hidden on small screens */}
      <div className="hidden lg:flex lg:w-1/2 bg-brand-dark flex-col justify-between p-12 text-white">
        <div>
          <Logo />
        </div>
        <div className="max-w-md">
          <h1 className="text-4xl font-bold tracking-tight mb-4 text-white">
            Hybrid Credibility Assessment
          </h1>
          <p className="text-slate-300 text-lg leading-relaxed">
            InfoTrust leverages advanced AI analysis, rule-based heuristics, and narrative tracking to accurately detect misinformation and establish trust.
          </p>
        </div>
        <div className="text-sm text-slate-400">
          &copy; {new Date().getFullYear()} InfoTrust Platform. All rights reserved.
        </div>
      </div>

      {/* Form Side */}
      <div className="flex-1 flex flex-col justify-center px-4 sm:px-6 lg:px-20 xl:px-24 bg-slate-50 lg:bg-white">
        {/* Mobile Logo */}
        <div className="lg:hidden mb-8 flex justify-center">
          <Logo />
        </div>
        
        <Outlet />
      </div>
    </div>
  );
}
