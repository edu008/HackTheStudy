import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '@/components/ui/use-toast';
import { User, AuthResponse } from '@/types';
import * as authService from '@/lib/api/authService';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  signIn: (provider: string) => Promise<void>;
  signOut: () => Promise<void>;
  addCredits: (amount: number) => void;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  // Sichere Verwendung von useNavigate mit Fallback für Umgebungen ohne Router
  let navigate;
  try {
    navigate = useNavigate();
  } catch (error) {
    // Fallback für Umgebungen ohne Router
    navigate = (path: string) => {
      console.log(`Navigation zu ${path} würde erfolgen, ist aber nicht verfügbar.`);
      // Optional: window.location.href = path; für echte Navigation
    };
  }

  // Lade Benutzer aus dem localStorage und prüfe die Token-Gültigkeit beim Start
  useEffect(() => {
    const checkAuth = async () => {
      try {
        setIsLoading(true);
        const storedUser = authService.getStoredUser();
        
        if (storedUser && authService.isAuthenticated()) {
          try {
            // Hole aktuelles Benutzerprofil, um Token-Gültigkeit zu prüfen
            const currentUser = await authService.getUserProfile();
            setUser(currentUser);
          } catch (error) {
            // Bei Fehler (z.B. ungültiges Token) - Benutzer ausloggen
            await authService.logout();
            setUser(null);
          }
        } else {
          setUser(null);
        }
      } catch (error) {
        console.error("Fehler beim Prüfen der Authentifizierung:", error);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Anmeldung mit OAuth-Provider
  const signIn = async (provider: string) => {
    setIsLoading(true);
    try {
      // Starte den OAuth-Flow
      authService.initiateOAuthLogin(provider);
    } catch (error) {
      console.error("Anmeldefehler:", error);
      toast({
        title: "Anmeldung fehlgeschlagen",
        description: "Die Anmeldung mit dem ausgewählten Provider ist fehlgeschlagen. Bitte versuche es erneut.",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Abmeldung
  const signOut = async () => {
    setIsLoading(true);
    try {
      await authService.logout();
      setUser(null);
      
      // Session-ID beim Abmelden löschen
      localStorage.removeItem("current_session_id");
      
      toast({
        title: "Abgemeldet",
        description: "Du wurdest erfolgreich abgemeldet."
      });
      
      // Zur Startseite navigieren
      navigate('/');
    } catch (error) {
      console.error("Fehler beim Abmelden:", error);
      toast({
        title: "Fehler beim Abmelden",
        description: "Es ist ein Problem aufgetreten. Bitte versuche es erneut.",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Credits hinzufügen (wird später mit dem Backend verbunden)
  const addCredits = (amount: number) => {
    if (user) {
      const updatedUser = { 
        ...user, 
        credits: user.credits + amount 
      };
      setUser(updatedUser);
      localStorage.setItem('exammaster_user', JSON.stringify(updatedUser));
      
      toast({
        title: "Credits hinzugefügt",
        description: `${amount} Credits wurden deinem Konto gutgeschrieben.`
      });
    }
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, signIn, signOut, addCredits, setUser }}>
      {children}
    </AuthContext.Provider>
  );
};
