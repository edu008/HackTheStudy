import { useEffect, useState } from 'react';
import axios from 'axios';

function App() {
  const [sessionId, setSessionId] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuthAndCreateSession = async () => {
      try {
        setLoading(true);
        
        const token = localStorage.getItem('authToken');
        
        if (token) {
          const config = {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          };
          
          const response = await axios.get('/api/auth/check-auth', config);
          
          if (response.data.authenticated) {
            setIsAuthenticated(true);
            setSessionId(response.data.session_id);
            
            if (response.data.user) {
              setUser(response.data.user);
            }
            
            console.log('Authentifizierung erfolgreich, neue Session erstellt:', response.data.session_id);
          } else {
            localStorage.removeItem('authToken');
            setIsAuthenticated(false);
            
            await createNewSession();
          }
        } else {
          setIsAuthenticated(false);
          await createNewSession();
        }
      } catch (error) {
        console.error('Fehler bei der Authentifizierungsprüfung:', error);
        
        await createNewSession();
        
        if (error.response && error.response.status === 401) {
          localStorage.removeItem('authToken');
          setIsAuthenticated(false);
        }
      } finally {
        setLoading(false);
      }
    };
    
    const createNewSession = async () => {
      try {
        const response = await axios.get('/api/uploads/new-session');
        setSessionId(response.data.session_id);
        console.log('Neue Session für anonymen Benutzer erstellt:', response.data.session_id);
      } catch (error) {
        console.error('Fehler beim Erstellen einer neuen Session:', error);
      }
    };
    
    checkAuthAndCreateSession();
    
    const handleBeforeUnload = () => {
      console.log('Seite wird neu geladen, Session wird beim Neuladen neu erstellt');
    };
    
    window.addEventListener('beforeunload', handleBeforeUnload);
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, []);

  return (
    <div className="app">
      {loading ? (
        <div className="loading">Laden...</div>
      ) : (
        <YourMainComponent 
          sessionId={sessionId}
          isAuthenticated={isAuthenticated}
          user={user}
        />
      )}
    </div>
  );
}

export default App; 