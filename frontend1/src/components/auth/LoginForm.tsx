import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useDispatch, useSelector } from 'react-redux';
import { Button, TextField, Link, FormHelperText, Alert } from '@mui/material';
import { login, clearError } from '@/store/slices/authSlice';
import { AppDispatch, RootState } from '@/store';
import useAuth from '@/hooks/useAuth';
import EmailIcon from '@mui/icons-material/Email';
import LockIcon from '@mui/icons-material/Lock';
import Divider from '@mui/material/Divider';
import GoogleIcon from '@mui/icons-material/Google';
import { useRouter } from 'next/navigation';

interface LoginFormData {
  email: string;
  password: string;
}

const LoginForm: React.FC = () => {
  const { register, handleSubmit, formState: { errors } } = useForm<LoginFormData>();
  const dispatch = useDispatch<AppDispatch>();
  const router = useRouter();
  const { loading } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const authError = useSelector((state: RootState) => state.auth.error);

  // Fehlermeldung beim Komponentenwechsel zurücksetzen
  useEffect(() => {
    return () => {
      dispatch(clearError());
    };
  }, [dispatch]);

  const onSubmit = async (data: LoginFormData) => {
    try {
      // Fehlermeldung zurücksetzen, wenn ein neuer Login-Versuch gestartet wird
      if (authError) {
        dispatch(clearError());
      }

      const result = await dispatch(login(data));
      if (result.meta.requestStatus === 'fulfilled') {
        router.push('/dashboard');
        return;
      }
    } catch (error) {
      console.error('Login-Fehler:', error);
    }
  };

  const handleGoogleLogin = () => {
    // Redirect to Google OAuth endpoint
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL}/auth/google`;
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {authError && (
        <Alert severity="error" className="mb-4" onClose={() => dispatch(clearError())}>
          {authError === 'Failed to login' ? 'Ungültige E-Mail oder Passwort' : authError}
        </Alert>
      )}

      <div className="flex items-center space-x-2">
        <EmailIcon color="primary" />
        <TextField
          fullWidth
          label="Email"
          variant="outlined"
          {...register('email', { 
            required: 'Email ist erforderlich',
            pattern: {
              value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
              message: 'Ungültige E-Mail-Adresse'
            }
          })}
          error={!!errors.email}
          helperText={errors.email?.message}
          disabled={loading}
        />
      </div>

      <div className="flex items-center space-x-2">
        <LockIcon color="primary" />
        <TextField
          fullWidth
          label="Passwort"
          type={showPassword ? 'text' : 'password'}
          variant="outlined"
          {...register('password', { 
            required: 'Passwort ist erforderlich',
            minLength: {
              value: 6,
              message: 'Passwort muss mindestens 6 Zeichen lang sein'
            }
          })}
          error={!!errors.password}
          helperText={errors.password?.message}
          disabled={loading}
        />
      </div>

      <div className="flex justify-between items-center">
        <div className="flex items-center">
          <input
            id="show-password"
            type="checkbox"
            className="mr-2"
            checked={showPassword}
            onChange={() => setShowPassword(!showPassword)}
          />
          <label htmlFor="show-password" className="text-sm cursor-pointer">Passwort anzeigen</label>
        </div>
        <Link href="/auth/reset-password" className="text-sm text-blue-600 hover:underline">
          Passwort vergessen?
        </Link>
      </div>

      <Button
        type="submit"
        fullWidth
        variant="contained"
        color="primary"
        disabled={loading}
        className="py-3"
      >
        {loading ? 'Anmeldung läuft...' : 'Anmelden'}
      </Button>

      <Divider className="my-4">oder</Divider>

      <Button
        fullWidth
        variant="outlined"
        startIcon={<GoogleIcon />}
        onClick={handleGoogleLogin}
        disabled={loading}
        className="py-3"
      >
        Mit Google fortfahren
      </Button>

      <div className="text-center mt-4">
        <span className="text-sm">Noch kein Konto?</span>{' '}
        <Link href="/auth/register" className="text-sm text-blue-600 hover:underline">
          Jetzt registrieren
        </Link>
      </div>
    </form>
  );
};

export default LoginForm; 