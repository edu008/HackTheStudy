import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Skeleton } from '@/components/ui/skeleton';
import axios from 'axios';
import { useToast } from '@/hooks/use-toast';
import { motion } from 'framer-motion';
import { 
  FileText, Clock, Layers, BookOpen, HelpCircle, 
  Upload, Plus, RefreshCw, PlusCircle 
} from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';
import { 
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import React from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { API_URL, axiosInstance } from '../lib/api';

interface SessionActivity {
  id: string;
  activity_type: string;
  title: string;
  main_topic?: string;
  subtopics?: string[];
  session_id: string;
  details?: any;
  timestamp: string;
}

interface SessionData {
  id: string;
  mainTopic: string;
  timestamp: string;
  activities: SessionActivity[];
  primaryType: string;
  flashcardCount?: number;
  questionCount?: number;
  subtopics?: string[];
}

// Füge eine Props-Definition mit dem onSessionSelect-Parameter hinzu
interface UserHistoryProps {
  onSessionSelect?: (sessionId: string, activityType: string, mainTopic: string) => void;
}

const UserHistory: React.FC<UserHistoryProps> = ({ onSessionSelect }) => {
  const [activities, setActivities] = useState<SessionActivity[]>([]);
  const [sessions, setSessions] = useState<SessionData[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingSession, setLoadingSession] = useState<string | null>(null);
  const [mainTopic, setMainTopic] = useState<string>("");
  const [flashcards, setFlashcards] = useState<any[]>([]);
  const [questions, setQuestions] = useState<any[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user, refreshUserCredits } = useAuth();
  const { t, i18n } = useTranslation();

  // loadActivities als useCallback definieren, um sicherzustellen, dass es stabil ist
  const loadActivities = useCallback(async () => {
    // Prüfen ob ein Benutzer vorhanden ist
    if (!user) {
      console.log("Kein Benutzer angemeldet, lade keine History-Daten");
      return;
    }
    
    if (loading) {
      console.log("Ladevorgang bereits aktiv, überspringe...");
      return; // Verhindere parallele Aufrufe
    }
    
    console.log("Starte Laden der History-Daten...");
    setLoading(true);
    
    try {
      const token = localStorage.getItem('exammaster_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      console.log("Sende API-Anfrage für History-Daten...");
      const response = await axios.get(`${API_URL}/api/v1/user-history`, { 
        headers,
        withCredentials: true 
      });
      
      if (response.data.success && Array.isArray(response.data.activities)) {
        console.log(`${response.data.activities.length} Aktivitäten geladen.`);
        setActivities(response.data.activities);
      } else {
        console.warn("⚠️ Keine Aktivitäten gefunden.");
        setActivities([]);
      }
    } catch (error) {
      console.error("❌ Fehler beim Abrufen der Aktivitäten:", error);
      toast({
        title: t('common.error'),
        description: t('dashboard.historySection.loadError', 'Die Aktivitäten konnten nicht geladen werden.'),
        variant: "destructive",
      });
    } finally {
      setLoading(false);
      console.log("Laden der History-Daten abgeschlossen.");
    }
  }, [toast, user, t]); // Entferne loading aus den Abhängigkeiten, damit es nicht bei jeder Änderung ausgelöst wird

  // Initialer Ladevorgang - nur einmal beim Mounten
  useEffect(() => {
    if (!isInitialized && user) {
      console.log("Initialisiere History-Komponente und lade Daten...");
      setIsInitialized(true);
      loadActivities();
    }
  }, [user, isInitialized, loadActivities]);

  // Cleanup Funktion
  useEffect(() => {
    return () => {
      // Hier können ggf. Timer oder andere Ressourcen bereinigt werden
      console.log("UserHistory Component unmounted");
    };
  }, []);

  useEffect(() => {
    if (activities.length > 0) {
      // Filtere nur Aktivitäten mit session_id und relevanten Typen
      const relevantActivities = activities.filter(activity => 
        activity.session_id && ['upload', 'flashcard', 'question'].includes(activity.activity_type)
      );

      const sessionMap = new Map<string, SessionData>();
      
      relevantActivities.forEach(activity => {
        const sessionId = activity.session_id;
        
        if (!sessionMap.has(sessionId)) {
          // Extrahiere main_topic aus details, falls vorhanden
          let mainTopic = activity.main_topic || "Unbenanntes Thema";
          let subtopics: string[] = activity.subtopics || [];
          
          if (activity.details) {
            if (activity.details.main_topic) {
              mainTopic = activity.details.main_topic;
            }
            if (activity.details.subtopics) {
              subtopics = activity.details.subtopics;
            }
          }
          
          sessionMap.set(sessionId, {
            id: sessionId,
            mainTopic: mainTopic,
            timestamp: activity.timestamp,
            activities: [],
            primaryType: activity.activity_type,
            subtopics: subtopics
          });
        }
        
        const session = sessionMap.get(sessionId)!;
        session.activities.push(activity);
        
        // Setze den primaryType auf 'upload', wenn eine Upload-Aktivität vorhanden ist
        if (activity.activity_type === 'upload') {
          session.primaryType = 'upload';
        }
        
        // Zähle Flashcards und Questions
        if (activity.activity_type === 'flashcard') {
          session.flashcardCount = (session.flashcardCount || 0) + 1;
        } else if (activity.activity_type === 'question') {
          session.questionCount = (session.questionCount || 0) + 1;
        }
      });
      
      const sessionList = Array.from(sessionMap.values()).sort((a, b) => 
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      
      setSessions(sessionList);
    }
  }, [activities]);

  // Verwende die i18n Locale für die Datumsformatierung
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat(i18n.language === 'de' ? 'de-DE' : 'en-US', { 
      day: '2-digit', 
      month: '2-digit', 
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  };

  // Funktion zum Generieren neuer Inhalte für eine bestehende Session
  const generateNewContent = async (sessionId: string, contentType: 'flashcards' | 'questions' | 'topics') => {
    setLoadingSession(sessionId);
    try {
      const token = localStorage.getItem('exammaster_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      const response = await axios.post(
        `${API_URL}/api/v1/generate`, 
        { 
          sessionId, 
          contentType 
        }, 
        { 
          headers,
          withCredentials: true 
        }
      );
      
      if (response.data.success) {
        toast({
          title: t('dashboard.historySection.contentGenerated', 'Inhalte generiert'),
          description: t(`dashboard.historySection.${contentType}Generated`, `Neue ${contentType} wurden erfolgreich generiert.`),
        });
        
        // Lade die Aktivitäten neu, um die neuen Inhalte anzuzeigen
        await loadActivities();
        
        // Lade die Session mit den neuen Inhalten
        await handleSessionClick(sessions.find(s => s.id === sessionId)!);
      } else {
        throw new Error(t('dashboard.historySection.generateError', `Fehler beim Generieren von ${contentType}`));
      }
    } catch (error) {
      console.error(`❌ Fehler beim Generieren von ${contentType}:`, error);
      toast({
        title: t('common.error'),
        description: t(`dashboard.historySection.${contentType}GenerateError`, `Die ${contentType} konnten nicht generiert werden.`),
        variant: "destructive",
      });
    } finally {
      setLoadingSession(null);
    }
  };
  
  // Funktion zum Laden zusätzlicher Prüfungen für eine bestehende Session
  const loadAdditionalExam = async (sessionId: string) => {
    setLoadingSession(sessionId);
    try {
      const token = localStorage.getItem('exammaster_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      const response = await axios.post(
        `${API_URL}/api/v1/load-exam`, 
        { sessionId }, 
        { 
          headers,
          withCredentials: true 
        }
      );
      
      if (response.data.success) {
        toast({
          title: "Prüfung hinzugefügt",
          description: "Zusätzliche Prüfung wurde erfolgreich geladen und der Session hinzugefügt.",
        });
        
        // Lade die Aktivitäten neu, um die neuen Inhalte anzuzeigen
        await loadActivities();
        
        // Lade die Session mit den neuen Inhalten
        await handleSessionClick(sessions.find(s => s.id === sessionId)!);
      } else {
        throw new Error("Fehler beim Laden der zusätzlichen Prüfung");
      }
    } catch (error) {
      console.error("❌ Fehler beim Laden der zusätzlichen Prüfung:", error);
      toast({
        title: "Fehler",
        description: "Die zusätzliche Prüfung konnte nicht geladen werden.",
        variant: "destructive",
      });
    } finally {
      setLoadingSession(null);
    }
  };
  
  // Funktion zum Starten einer neuen Session und Navigieren zur Upload-Schnittstelle
  const startNewSession = () => {
    // Navigiere zur Upload-Seite
    navigate('/upload', {
      state: {
        newSession: true,
        resetData: true
      }
    });
    
    toast({
      title: t('dashboard.historySection.newSession', 'Neue Session'),
      description: t('dashboard.historySection.uploadPrompt', 'Starte eine neue Session. Bitte lade deine Prüfungen hoch.'),
    });
  };

  // Funktion zum Öffnen einer Session
  const handleSessionClick = async (session: SessionData) => {
    setLoadingSession(session.id);
    console.log(`Versuche, Session zu laden: ${session.id}, Hauptthema: ${session.mainTopic}`);
    
    try {
      // Aktualisiere zuerst die Credits, um sicherzustellen, dass wir den aktuellen Stand haben
      if (user) {
        try {
          // Verwende refreshUserCredits aus dem Auth-Kontext
          await refreshUserCredits();
          console.log("Credits wurden aktualisiert vor dem Laden der Session");
        } catch (creditError) {
          console.error("Fehler beim Aktualisieren der Credits:", creditError);
          // Wir setzen den Vorgang trotzdem fort
        }
      }
      
      const token = localStorage.getItem('exammaster_token');
      
      if (!token) {
        console.warn("Kein Auth-Token gefunden!");
        toast({
          title: "Nicht authentifiziert",
          description: "Bitte melde dich an, um deine Sessions zu laden.",
          variant: "destructive",
        });
        setLoadingSession(null);
        return;
      }
      
      const headers = { 
        Authorization: `Bearer ${token}`,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
      };
      
      // Cache-busting Parameter hinzufügen
      const timestamp = new Date().getTime();
      
      console.log(`Sende Anfrage an: ${API_URL}/api/v1/results/${session.id}?nocache=${timestamp}`);
      
      // Kurzes Warten, um sicherzustellen, dass der Server bereit ist
      console.log("Warte 1 Sekunde...");
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      console.log("Sende API-Anfrage für Session-Daten...");
      const response = await axiosInstance.get(`/api/v1/results/${session.id}?nocache=${timestamp}`);
      
      console.log("API-Antwort erhalten:", response.status);
      
      if (response.data && response.data.success) {
        const sessionData = response.data.data;
        
        if (!sessionData) {
          console.error("Session-Daten fehlen in der API-Antwort:", response.data);
          throw new Error("Session-Daten nicht gefunden");
        }
        
        const flashcardCount = sessionData.flashcards?.length || 0;
        const questionCount = sessionData.test_questions?.length || 0;
        
        console.log(`Geladene Session-Daten: ${flashcardCount} Flashcards, ${questionCount} Fragen`);
        
        // Verarbeitung
        if (sessionData.analysis?.processing_status === "processing" && 
            flashcardCount === 0 && questionCount === 0) {
          
          toast({
            title: "Sitzung wird noch verarbeitet",
            description: "Die Daten werden noch verarbeitet. Bitte warten Sie einen Moment.",
          });
          
          console.log("Session wird noch verarbeitet, warte 5 Sekunden für erneuten Versuch...");
          await new Promise(resolve => setTimeout(resolve, 5000));
          
          const newTimestamp = new Date().getTime();
          console.log(`Wiederhole Anfrage: ${API_URL}/api/v1/results/${session.id}?nocache=${newTimestamp}`);
          
          const retryResponse = await axiosInstance.get(`/api/v1/results/${session.id}?nocache=${newTimestamp}`);
          
          if (retryResponse.data && retryResponse.data.success) {
            const updatedSessionData = retryResponse.data.data;
            
            if (!updatedSessionData) {
              console.error("Aktualisierte Session-Daten fehlen in der Antwort:", retryResponse.data);
              throw new Error("Aktualisierte Session-Daten nicht gefunden");
            }
            
            console.log("Navigation zur Hauptseite mit aktualisierten Daten...");
            // Save the session ID to localStorage before navigating
            localStorage.setItem('current_session_id', session.id);
            
            navigate(`/`, {
              state: {
                sessionId: session.id,
                flashcards: updatedSessionData.flashcards || [],
                questions: updatedSessionData.test_questions || [],
                analysis: updatedSessionData.analysis,
                forceReload: true
              },
            });
            
            toast({
              title: "Analyse geladen",
              description: `Die Analyse "${session.mainTopic}" wurde erfolgreich geladen mit ${updatedSessionData.flashcards?.length || 0} Karten und ${updatedSessionData.test_questions?.length || 0} Fragen.`,
            });
            
            return;
          }
        }
        
        // Standard-Ablauf, wenn alles in Ordnung ist
        console.log("Navigation zur Hauptseite mit Session-Daten...");
        // Save the session ID to localStorage before navigating
        localStorage.setItem('current_session_id', session.id);
        
        navigate(`/`, {
          state: {
            sessionId: session.id,
            flashcards: sessionData.flashcards || [],
            questions: sessionData.test_questions || [],
            analysis: sessionData.analysis,
            forceReload: true
          },
        });
        
        toast({
          title: "Analyse geladen",
          description: `Die Analyse "${session.mainTopic}" wurde erfolgreich geladen mit ${flashcardCount} Karten und ${questionCount} Fragen.`,
        });

        // Aktualisiere den timestamp, um die Session nach vorne zu bewegen
        if (session.activities && session.activities.length > 0) {
          const activity = session.activities[0];
          console.log(`Aktualisiere Timestamp für Aktivität: ${activity.id}`);
          
          try {
            await axios.put(`${API_URL}/api/v1/user-history/${activity.id}`, {}, { 
              headers,
              withCredentials: true 
            });
            await loadActivities(); // Lade die Historie neu
          } catch (updateError) {
            console.error("Fehler beim Aktualisieren des Timestamps:", updateError);
            // Kein kritischer Fehler, daher keine Toast-Nachricht
          }
        }
      } else {
        if (response.data) {
          console.error("API-Antwort enthält Fehler:", response.data);
          throw new Error(response.data.message || "Keine Daten gefunden");
        } else {
          throw new Error("Unerwartete API-Antwort");
        }
      }
    } catch (error: any) {
      console.error("❌ Fehler beim Laden der Session:", error);
      let errorMessage = "Die Daten für diese Session konnten nicht geladen werden.";
      let isCreditsError = false;
      let creditsRequired = 0;
      
      if (error.response) {
        // Der Request wurde gemacht und der Server antwortete mit einem Statuscode
        // der außerhalb von 2xx liegt
        console.error("Status:", error.response.status);
        console.error("Daten:", error.response.data);
        console.error("Headers:", error.response.headers);
        
        if (error.response.status === 400) {
          // Überprüfen, ob es sich um einen "nicht genügend Credits"-Fehler handelt
          const errorData = error.response.data;
          
          if (errorData && errorData.error && errorData.error.message && 
              errorData.error.message.includes("Nicht genügend Credits")) {
            
            // Extrahiere die benötigten Credits aus der Fehlermeldung
            const creditsMatch = errorData.error.message.match(/Benötigt: (\d+) Credits/);
            creditsRequired = creditsMatch ? parseInt(creditsMatch[1]) : 0;
            
            isCreditsError = true;
            errorMessage = `Nicht genügend Credits für diese Aktion. Es werden ${creditsRequired} Credits benötigt.`;
            
            // Prüfe, ob der Benutzer laut Frontend eigentlich genug Credits haben sollte
            if (user && user.credits >= creditsRequired) {
              errorMessage = `Synchronisierungsproblem mit Credits erkannt. Laut Frontend: ${user.credits} Credits, Benötigt: ${creditsRequired} Credits.`;
            }
          }
        } else if (error.response.status === 404) {
          errorMessage = "Diese Session existiert nicht mehr.";
        } else if (error.response.status === 403) {
          errorMessage = "Du hast keine Berechtigung, diese Session zu laden.";
        } else if (error.response.status >= 500) {
          errorMessage = "Der Server hat einen Fehler beim Laden der Session.";
        }
      } else if (error.request) {
        // Der Request wurde gemacht aber keine Antwort erhalten
        console.error("Keine Antwort erhalten:", error.request);
        errorMessage = "Keine Antwort vom Server erhalten. Bitte überprüfe deine Internetverbindung.";
      } else {
        // Etwas anderes ist beim Setup des Requests schief gegangen
        console.error("Fehler:", error.message);
      }
      
      if (isCreditsError) {
        // Spezielle Behandlung für Credits-Fehler mit mehreren Optionen
        toast({
          title: "Credits-Problem erkannt",
          description: (
            <div className="flex flex-col space-y-3">
              <p>{errorMessage}</p>
              <div className="flex flex-col sm:flex-row gap-2">
                <Button 
                  variant="default" 
                  size="sm"
                  onClick={() => {
                    navigate('/payment');
                  }}
                >
                  Credits aufladen
                </Button>
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={async () => {
                    // Aktualisiere die Credits und versuche es erneut
                    await refreshUserCredits();
                    toast({
                      title: "Credits aktualisiert",
                      description: "Bitte versuche es erneut, die Credits wurden aktualisiert.",
                    });
                  }}
                >
                  Credits aktualisieren
                </Button>
              </div>
            </div>
          ),
          variant: "destructive",
          duration: 15000, // Längere Anzeigedauer
        });
      } else {
        // Standard-Fehlerbehandlung für andere Fehler
        toast({
          title: "Fehler beim Laden",
          description: errorMessage,
          variant: "destructive",
        });
      }
    } finally {
      setLoadingSession(null);
    }
  };
  
  // Verhindert, dass das Klicken auf die Dropdown-Menüs die Session öffnet
  const handleDropdownClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  return (
    <div className="py-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">{t('dashboard.historySection.analyzedSessions', 'Analysierte Sessions')}</h3>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={loadActivities} 
          disabled={loading}
        >
          <RefreshCw className="h-4 w-4 mr-1" />
          {t('dashboard.historySection.refresh', 'Aktualisieren')}
        </Button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          <div>{t('dashboard.historySection.noSessions', 'Keine analysierten Sessions gefunden.')}</div>
        </div>
      ) : (
        <ScrollArea className="h-[calc(100vh-180px)] pr-4">
          <div className="grid grid-cols-1 gap-3 pr-2 pb-6">
            {sessions.map((session) => (
              <motion.div
                key={session.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                whileHover={{ scale: 1.01 }}
                onClick={() => handleSessionClick(session)}
              >
                <Card className={`relative overflow-hidden p-4 cursor-pointer hover:shadow-md transition-all duration-300
                              ${loadingSession === session.id ? 'opacity-70' : ''}`}>
                  {loadingSession === session.id && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-sm z-20">
                      <div className="h-8 w-8 rounded-full border-3 border-primary border-t-transparent animate-spin" />
                    </div>
                  )}
                  
                  <div className="relative z-10">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h4 className="font-medium text-base truncate">{session.mainTopic}</h4>
                        <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                          <Clock className="h-3 w-3" />
                          <span>{formatDate(session.timestamp)}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-muted-foreground">
                        {session.flashcardCount && session.flashcardCount > 0 && (
                          <div className="flex items-center gap-1" title={t('flashcards.title', 'Flashcards')}>
                            <BookOpen className="h-4 w-4" />
                            <span className="text-xs">{session.flashcardCount}</span>
                          </div>
                        )}
                        {session.questionCount && session.questionCount > 0 && (
                          <div className="flex items-center gap-1" title={t('tests.title', 'Testfragen')}>
                            <HelpCircle className="h-4 w-4" />
                            <span className="text-xs">{session.questionCount}</span>
                          </div>
                        )}
                      </div>
                    </div>
                    
                    {session.subtopics && session.subtopics.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {session.subtopics.slice(0, 3).map((topic, index) => (
                          <span key={index} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground">
                            {topic}
                          </span>
                        ))}
                        {session.subtopics.length > 3 && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground">
                            +{session.subtopics.length - 3}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </Card>
              </motion.div>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
};

// Mit React.memo wrappen, um unnötige Rerenders zu vermeiden
export default React.memo(UserHistory);
