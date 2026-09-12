export function ValidationMessage({ message }: { message?: string }) {
  if (!message) return null;
  
  return (
    <p className="text-sm text-red-600 mt-1.5 font-medium" role="alert">
      {message}
    </p>
  );
}
