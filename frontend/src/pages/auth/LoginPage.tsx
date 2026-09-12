import { FormContainer } from "../../components/ui/FormContainer";

export function LoginPage() {
  return (
    <FormContainer 
      title="Welcome back" 
      description="Enter your credentials to access your account."
    >
      <form className="space-y-5" onSubmit={(e) => e.preventDefault()}>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1" htmlFor="email">
            Email address
          </label>
          <input
            id="email"
            type="email"
            placeholder="name@example.com"
            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition-shadow disabled:bg-slate-50 disabled:text-slate-500"
            disabled
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            placeholder="••••••••"
            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition-shadow disabled:bg-slate-50 disabled:text-slate-500"
            disabled
          />
        </div>

        <button
          type="button"
          className="w-full flex justify-center items-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors disabled:opacity-70"
          disabled
        >
          Sign in
        </button>

        <p className="text-center text-sm text-slate-600 mt-6">
          Don't have an account?{" "}
          <a href="/register" className="font-medium text-primary-600 hover:text-primary-500">
            Register now
          </a>
        </p>
      </form>
    </FormContainer>
  );
}
