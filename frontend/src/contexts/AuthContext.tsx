import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from '@/components/ui/use-toast';
import axios from 'axios';

interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  credits: number;
}

interface Activity {
  id: string;
  type: string;
  title: string;
  details?: any;
  timestamp: string;
}

interface Payment {
  id: string;
  amount: number;
  credits: number;
  payment_method: string;
  transaction_id: string;
  status: string;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  activities: Activity[];
  payments: Payment[];
  signIn: (provider: string) => Promise<void>;
  signOut: () => void;
  addCredits: (amount: number, paymentMethod: string) => Promise<boolean>;
  recordActivity: (type: string, title: string, details?: any) => Promise<void>;
  fetchActivities: () => Promise<void>;
  fetchPayments: () => Promise<void>;
  refreshUserCredits: () => Promise<void>;
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
  const [activities, setActivities] = useState<Activity[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const navigate = useNavigate();
  const location = useLocation();
  
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
  const FRONTEND_URL = import.meta.env.VITE_FRONTEND_URL || 'http://localhost:8080';
  const PAYMENT_API_URL = import.meta.env.VITE_PAYMENT_API_URL || 'http://localhost:5001';

  // Check for auth callback
  useEffect(() => {
    const handleAuthCallback = async () => {
      if (location.pathname === '/auth-callback') {
        const params = new URLSearchParams(location.search);
        const token = params.get('token');
        
        if (token) {
          try {
            // Fetch user data with timeout
            const response = await axios.get(`${API_URL}/api/v1/auth/user`, {
              headers: {
                Authorization: `Bearer ${token}`
              },
              withCredentials: true,
              timeout: 5000 // 5 second timeout
            });
            
            if (response.data) {
              const userData = response.data; // Data is now directly at the top level
              const userObj = {
                id: userData.id.toString(),
                name: userData.name,
                email: userData.email,
                avatar: userData.avatar,
                credits: userData.credits
              };
              
              setUser(userObj);
              localStorage.setItem('exammaster_token', token);
              localStorage.setItem('exammaster_user', JSON.stringify(userObj));
              
              toast({
                title: "Successfully signed in",
                description: `Welcome, ${userData.name}!`,
              });
              
              // Redirect to home page
              navigate('/');
            }
          } catch (error) {
            console.error('Auth callback error:', error);
            
            // Create a fallback demo user if we can't connect to the backend
            const mockUser: User = {
              id: `user_${Math.random().toString(36).substr(2, 9)}`,
              name: 'Demo User (Fallback)',
              email: 'demo@example.com',
              avatar: `https://ui-avatars.com/api/?name=Demo+User&background=random`,
              credits: 100
            };
            
            setUser(mockUser);
            localStorage.setItem('exammaster_token', 'mock_token');
            localStorage.setItem('exammaster_user', JSON.stringify(mockUser));
            
            toast({
              title: "⚠️ Limited functionality mode",
              description: "Backend connection failed. Using demo mode with limited functionality.",
              variant: "destructive"
            });
            
            navigate('/');
          }
        }
      }
    };
    
    handleAuthCallback();
  }, [location, navigate]);

  // Load user from token on initial render
  useEffect(() => {
    const loadUser = async () => {
      const token = localStorage.getItem('exammaster_token');
      const storedUser = localStorage.getItem('exammaster_user');
      
      if (token) {
        try {
          // First check if we have a stored user (for offline/fallback use)
          if (storedUser) {
            try {
              const parsedUser = JSON.parse(storedUser);
              setUser(parsedUser);
            } catch (parseError) {
              console.error('Error parsing stored user:', parseError);
              // Continue with API call if parsing fails
            }
          }
          
          // Try to get fresh user data from backend with timeout
          const response = await axios.get(`${API_URL}/api/v1/auth/user`, {
            headers: {
              Authorization: `Bearer ${token}`
            },
            withCredentials: true,
            timeout: 5000 // 5 second timeout
          });
          
          if (response.data) {
            const userData = response.data; // Data is now directly at the top level
            const userObj = {
              id: userData.id.toString(),
              name: userData.name,
              email: userData.email,
              avatar: userData.avatar,
              credits: userData.credits
            };
            
            setUser(userObj);
            // Store user data for offline/fallback use
            localStorage.setItem('exammaster_user', JSON.stringify(userObj));
          }
        } catch (error) {
          console.error('Load user error:', error);
          
          // If we have a stored user, keep using it despite the API error
          if (storedUser) {
            try {
              const parsedUser = JSON.parse(storedUser);
              setUser(parsedUser);
              
              // Show a toast that we're using cached data
              toast({
                title: "⚠️ Offline mode",
                description: "Using cached user data. Some features may be limited.",
                variant: "default"
              });
            } catch (parseError) {
              console.error('Error parsing stored user after API error:', parseError);
              localStorage.removeItem('exammaster_token');
              localStorage.removeItem('exammaster_user');
            }
          } else {
            // If no stored user and API error, clear token
            localStorage.removeItem('exammaster_token');
          }
        }
      }
      setIsLoading(false);
    };
    
    loadUser();
  }, []);

  const signIn = async (provider: string) => {
    setIsLoading(true);
    try {
      // For demo mode only - can be removed in production
      if (provider === 'mock') {
        // Mock user data
        const mockUser: User = {
          id: `user_${Math.random().toString(36).substr(2, 9)}`,
          name: 'Demo User',
          email: 'demo@example.com',
          avatar: `https://ui-avatars.com/api/?name=Demo+User&background=random`,
          credits: 100
        };
        
        setUser(mockUser);
        localStorage.setItem('exammaster_token', 'mock_token');
        localStorage.setItem('exammaster_user', JSON.stringify(mockUser));
        
        toast({
          title: "Successfully signed in",
          description: `Welcome, ${mockUser.name}!`,
        });
        
        setIsLoading(false);
        navigate('/');
        return;
      }
      
      // Real OAuth authentication
      try {
        // First check if the backend is available
        const checkResponse = await fetch(`${API_URL}`, { 
          method: 'GET',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        
        if (!checkResponse.ok) {
          throw new Error('Backend server is not available');
        }
        
        // Redirect to OAuth provider
        window.location.href = `${API_URL}/api/v1/auth/login/${provider}`;
        // The rest of the flow is handled by the useEffect above
      } catch (error) {
        console.error('Backend connection error:', error);
        
        // Fallback to demo mode if backend is not available
        toast({
          title: "Backend connection failed",
          description: "Using demo mode instead. In production, this would connect to a real authentication server.",
          variant: "destructive"
        });
        
        // Create demo user as fallback
        const mockUser: User = {
          id: `user_${Math.random().toString(36).substr(2, 9)}`,
          name: 'Demo User (Fallback)',
          email: 'demo@example.com',
          avatar: `https://ui-avatars.com/api/?name=Demo+User&background=random`,
          credits: 100
        };
        
        setUser(mockUser);
        localStorage.setItem('exammaster_token', 'mock_token');
        localStorage.setItem('exammaster_user', JSON.stringify(mockUser));
        
        setIsLoading(false);
        navigate('/');
      }
    } catch (error) {
      console.error('Sign in error:', error);
      toast({
        title: "Sign in failed",
        description: "Could not sign in with the selected provider.",
        variant: "destructive"
      });
      setIsLoading(false);
    }
  };

  const signOut = async () => {
    try {
      // Try to call the backend logout endpoint
      try {
        await axios.get(`${API_URL}/api/v1/auth/logout`, { 
          withCredentials: true,
          timeout: 3000 // Add timeout to prevent hanging
        });
      } catch (apiError) {
        console.error('Backend logout API error:', apiError);
        // Continue with local logout even if the API call fails
      }
      
      // Always perform local logout actions
      localStorage.removeItem('exammaster_token');
      localStorage.removeItem('exammaster_user');
      setUser(null);
      setActivities([]);
      setPayments([]);
      
      toast({
        title: "Signed out",
        description: "You have been successfully signed out."
      });
      
      // Force navigation to home page
      window.location.href = '/';
    } catch (error) {
      console.error('Sign out error:', error);
      
      // Fallback: force logout anyway
      localStorage.removeItem('exammaster_token');
      localStorage.removeItem('exammaster_user');
      setUser(null);
      
      toast({
        title: "Sign out completed",
        description: "You have been signed out with some errors."
      });
      
      window.location.href = '/';
    }
  };

  const addCredits = async (amount: number, paymentMethod: string): Promise<boolean> => {
    try {
      // Wenn wir in einem Demo-Modus sind, fügen wir direkt Credits hinzu
      if (user && user.id.includes('mock') || localStorage.getItem('exammaster_token') === 'mock_token') {
        const newCredits = (user?.credits || 0) + amount;
        setUser(prev => prev ? { ...prev, credits: newCredits } : null);
        
        // Auch den gespeicherten Benutzer aktualisieren
        const storedUser = localStorage.getItem('exammaster_user');
        if (storedUser) {
          try {
            const parsedUser = JSON.parse(storedUser);
            parsedUser.credits = newCredits;
            localStorage.setItem('exammaster_user', JSON.stringify(parsedUser));
          } catch (parseError) {
            console.error('Error updating stored user credits:', parseError);
          }
        }
        
        toast({
          title: "Credits hinzugefügt",
          description: `${amount} Credits wurden Ihrem Konto gutgeschrieben. (Demo-Modus)`,
        });
        
        return true;
      }
      
      // In einer echten Umgebung verwenden wir Stripe
      // Beachten Sie, dass der tatsächliche Kreditgutschrift über den Webhook erfolgt
      // Wir leiten nur zur Checkout-Seite weiter, die addCredits-Funktion ist daher
      // ein Platzhalter für die Demo-Umgebung
      return true;
    } catch (error) {
      console.error('Error adding credits:', error);
      toast({
        title: "Fehler beim Hinzufügen von Credits",
        description: "Es gab ein Problem beim Hinzufügen von Credits. Bitte versuchen Sie es später erneut.",
        variant: "destructive"
      });
      return false;
    }
  };

  // Funktion, um die Kredite des Benutzers zu aktualisieren (nach erfolgreicher Zahlung)
  const refreshUserCredits = async () => {
    if (!user) return;
    
    try {
      const token = localStorage.getItem('exammaster_token');
      if (!token) return;
      
      const response = await axios.get(`${PAYMENT_API_URL}/api/payment/get-credits`, {
        withCredentials: true,
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      
      if (response.data) {
        setUser(prev => prev ? { ...prev, credits: response.data.credits } : null);
        
        // Auch den gespeicherten Benutzer aktualisieren
        const storedUser = localStorage.getItem('exammaster_user');
        if (storedUser) {
          try {
            const parsedUser = JSON.parse(storedUser);
            parsedUser.credits = response.data.credits;
            localStorage.setItem('exammaster_user', JSON.stringify(parsedUser));
          } catch (parseError) {
            console.error('Error updating stored user credits:', parseError);
          }
        }
      }
    } catch (error) {
      console.error('Error refreshing user credits:', error);
    }
  };
  
  const recordActivity = async (type: string, title: string, details?: any) => {
    if (!user) return;
    
    try {
      const response = await axios.post(
        `${API_URL}/api/v1/auth/activity`,
        { type, title, details },
        { 
          withCredentials: true,
          timeout: 5000 // 5 second timeout
        }
      );
      
      if (response.data.success) {
        // Update activities list
        setActivities(prev => [response.data.activity, ...prev].slice(0, 20));
      }
    } catch (error) {
      console.error('Record activity error:', error);
    }
  };
  
  const fetchActivities = async () => {
    if (!user) return;
    
    try {
      const response = await axios.get(`${API_URL}/api/v1/auth/activity`, { 
        withCredentials: true,
        timeout: 5000 // 5 second timeout
      });
      setActivities(response.data.data?.activities || []);
    } catch (error) {
      console.error('Fetch activities error:', error);
    }
  };
  
  const fetchPayments = async () => {
    if (!user) return;
    
    try {
      const response = await axios.get(`${API_URL}/api/v1/auth/payments`, { 
        withCredentials: true,
        timeout: 5000 // 5 second timeout
      });
      // Access the payments data from the correct nested structure
      setPayments(response.data.data?.payments || []);
    } catch (error) {
      console.error('Fetch payments error:', error);
    }
  };

  return (
    <AuthContext.Provider value={{ 
      user, 
      isLoading, 
      activities,
      payments,
      signIn, 
      signOut, 
      addCredits,
      recordActivity,
      fetchActivities,
      fetchPayments,
      refreshUserCredits
    }}>
      {children}
    </AuthContext.Provider>
  );
};
