import { createRoot } from 'react-dom/client'
import './i18n/i18n.ts'
import App from './App.tsx'
import './index.css'
import { axiosInstance } from './lib/api';
import { toast } from "@/components/ui/use-toast";

// Globale Axios-Interceptors konfigurieren
axiosInstance.interceptors.response.use(
  response => response,
  error => {
    // Allgemeine Protokollierung
    console.error('Axios Fehler:', error);

    try {
      // CORS-Fehler spezifisch behandeln
      if (error.message === 'Network Error') {
        console.error('CORS oder Netzwerkfehler:', error);
        
        toast({
          title: "Verbindungsproblem",
          description: "Es gibt ein Problem mit der Verbindung zum Server. Bitte versuchen Sie es später erneut.",
          variant: "destructive",
        });
      }
      
      // Allgemeine Fehlerbehandlung - sicherer Zugriff auf verschachtelte Eigenschaften
      const errorMessage = error?.response?.data?.error?.message || 'Ein unbekannter Fehler ist aufgetreten';
      
      // Verarbeite Statuscodes sicher
      const statusCode = error?.response?.status;
      
      if (statusCode === 401) {
        toast({
          title: "Nicht autorisiert",
          description: "Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
          variant: "destructive",
        });
      } else if (statusCode === 429) {
        toast({
          title: "Zu viele Anfragen",
          description: "Bitte warten Sie einen Moment und versuchen Sie es erneut.",
          variant: "destructive",
        });
      } else if (statusCode >= 500) {
        toast({
          title: "Serverfehler",
          description: "Ein Serverfehler ist aufgetreten. Unsere Techniker wurden informiert.",
          variant: "destructive",
        });
      }
    } catch (handlerError) {
      console.error('Fehler in der Axios-Fehlerbehandlung:', handlerError);
    }
    
    return Promise.reject(error);
  }
);

createRoot(document.getElementById("root")!).render(<App />);
