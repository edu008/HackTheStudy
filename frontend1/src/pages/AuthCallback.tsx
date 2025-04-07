import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

const AuthCallback = () => {
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { isLoading } = useAuth();

  useEffect(() => {
    // The actual authentication logic is handled in the AuthContext
    // This component just shows a loading state and handles errors
    
    const params = new URLSearchParams(location.search);
    const errorParam = params.get('error');
    
    if (errorParam) {
      setError(errorParam);
      setTimeout(() => {
        navigate('/signin');
      }, 3000);
    }
  }, [location, navigate]);

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <h1 className="text-2xl font-bold text-red-600 mb-4">Authentication Error</h1>
          <p className="mb-6">{error}</p>
          <p className="text-muted-foreground">Redirecting you back to sign in...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="max-w-md w-full text-center">
        <h1 className="text-2xl font-bold mb-4">Completing Authentication</h1>
        <div className="flex justify-center mb-6">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
        </div>
        <p className="text-muted-foreground">Please wait while we complete the authentication process...</p>
      </div>
    </div>
  );
};

export default AuthCallback;
