import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from '@/components/ui/use-toast';
import { handleOAuthCallback, saveAuthData } from '@/lib/api/authService';
import { useAuth } from '@/contexts/AuthContext';

const AuthCallback: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setUser } = useAuth();

  useEffect(() => {
    const processCallback = async () => {
      try {
        console.log("AuthCallback: Verarbeite Callback-Parameter", Object.fromEntries(searchParams));

        // Prüfe zunächst, ob ein JWT-Token direkt als Parameter übergeben wurde
        const token = searchParams.get('token');
        if (token) {
          console.log("AuthCallback: Token gefunden", token.substring(0, 20) + "...");
          
          // Das Backend hat direkt ein JWT-Token zurückgegeben
          // Mock-Benutzer erstellen (später durch API-Abruf ersetzen)
          const mockUser = {
            id: `user_${Date.now()}`,
            name: "Angemeldeter Benutzer",
            email: `user_${Date.now()}@example.com`,
            credits: 100
          };
          
          const authResponse = {
            user: mockUser,
            token: token,
            refreshToken: `mock_refresh_${Date.now()}`
          };
          
          saveAuthData(authResponse);
          setUser(mockUser);
          
          toast({
            title: "Erfolgreich angemeldet",
            description: "Du wurdest erfolgreich angemeldet.",
          });
          
          // Weiterleitung zur Tasks-Seite
          navigate('/tasks');
          return;
        }
        
        // Falls kein direktes Token, prüfe auf OAuth-Code
        const code = searchParams.get('code');
        console.log("AuthCallback: OAuth-Code", code ? "vorhanden" : "nicht vorhanden");
        
        if (!code && !token) {
          throw new Error('Keine Authentifizierungsparameter gefunden');
        }
        
        // Zu diesem Punkt sollten wir nicht kommen, wenn ein Token gefunden wurde
        toast({
          title: "Fehler bei der Anmeldung",
          description: "Unerwarteter Zustand in der Authentifizierung",
          variant: "destructive"
        });
        navigate('/signin');
      } catch (error) {
        console.error('Fehler bei der OAuth-Verarbeitung:', error);
        toast({
          title: "Anmeldung fehlgeschlagen",
          description: "Die Anmeldung ist fehlgeschlagen. Bitte versuche es erneut.",
          variant: "destructive"
        });
        // Weiterleitung zur Anmeldeseite
        navigate('/signin');
      }
    };

    processCallback();
  }, [navigate, searchParams, setUser]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-4">Verarbeite Anmeldung...</h1>
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
      </div>
    </div>
  );
};

export default AuthCallback; 