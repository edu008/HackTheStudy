import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Skeleton } from '@/components/ui/skeleton';
import axios from 'axios';
import { useToast } from '@/hooks/use-toast';
import { motion } from 'framer-motion';
import { 
  FileText, Clock, Layers, BookOpen, HelpCircle, 
  Upload, Plus, RefreshCw, PlusCircle, AlertCircle
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
import { useTranslation } from 'react-i18next';
import { API_URL, axiosInstance } from '../lib/api';

// --------- TYPES ---------
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

interface UserHistoryProps {
  onSessionSelect?: (sessionId: string, activityType: string, mainTopic: string) => void;
}

// --------- MAIN COMPONENT ---------
const UserHistory: React.FC<UserHistoryProps> = ({ onSessionSelect }) => {
  // --------- STATE ---------
  const [activities, setActivities] = useState<SessionActivity[]>([]);
  const [sessions, setSessions] = useState<SessionData[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingSession, setLoadingSession] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState<{ [key: string]: any }>({});
  
  // --------- HOOKS ---------
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user, refreshUserCredits } = useAuth();
  const { t, i18n } = useTranslation();

  // --------- FUNCTIONS ---------
  
  // Debugger-Hilfsfunktion
  const debug = useCallback((message: string, data?: any) => {
    console.log(`[UserHistory] ${message}`, data || '');
    
    // Debug-Informationen aktualisieren
    setDebugInfo(prev => ({
      ...prev,
      lastMessage: message,
      lastTimestamp: new Date().toISOString(),
      [message.replace(/[^a-zA-Z0-9]/g, '_')]: data || true
    }));
  }, []);

  // Laden der Aktivitäten
  const loadActivities = useCallback(async () => {
    if (!user) {
      debug("Kein Benutzer angemeldet");
      setSessions([]); // Setze Sessions explizit auf leeres Array
      return;
    }
    
    if (loading) {
      debug("Bereits am Laden...");
      return;
    }
    
    debug("Starte Ladevorgang");
    setLoading(true);
    
    try {
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        debug("Kein Token gefunden");
        setLoading(false);
        return;
      }
      
      debug("Rufe API auf...");
      
      // Hinzufügen eines Cache-Busting-Parameters
      const timestamp = Date.now();
      const url = `${API_URL}/api/v1/user-history?t=${timestamp}`;
      
      debug(`API-URL: ${url}`);
      
      const response = await axios.get(url, {
        headers: { 
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache'
        },
        withCredentials: true
      });
      
      debug("API-Antwort erhalten", {
        status: response.status,
        success: response.data?.success,
        itemCount: response.data?.activities?.length
      });
      
      if (response.data?.success && Array.isArray(response.data.activities)) {
        const rawActivities = response.data.activities;
        debug(`${rawActivities.length} Aktivitäten gefunden`);
        
        // Filtern und validieren
        const validActivities = rawActivities.filter(act => 
          act?.session_id && ['upload', 'flashcard', 'question'].includes(act.activity_type || '')
        );
        
        debug(`${validActivities.length} gültige Aktivitäten nach Filterung`);
        setActivities(validActivities);
      } else {
        debug("Keine Aktivitäten in der Antwort");
        setActivities([]);
      }
    } catch (error) {
      debug("Fehler beim Laden der Aktivitäten", error);
      toast({
        title: t('common.error'),
        description: t('dashboard.historySection.loadError', 'Die Aktivitäten konnten nicht geladen werden.'),
        variant: "destructive",
      });
    } finally {
      setLoading(false);
      debug("Ladevorgang abgeschlossen");
    }
  }, [user, loading, debug, toast, t]);

  // Erstellen der Sessions aus den Aktivitäten
  useEffect(() => {
    debug(`Processing ${activities.length} activities...`);
    
    if (activities.length === 0) {
      debug("Keine Aktivitäten vorhanden");
      setSessions([]);
      return;
    }
    
    try {
      const sessionMap = new Map<string, SessionData>();
      
      activities.forEach(activity => {
        debug(`Verarbeite Aktivität: ${activity.id}, Typ: ${activity.activity_type}, Session: ${activity.session_id}`);
        const sessionId = activity.session_id;
        
        if (!sessionMap.has(sessionId)) {
          // Neuen Session-Eintrag erstellen
          let mainTopic = activity.main_topic || "Unbenanntes Thema";
          let subtopics: string[] = activity.subtopics || [];
          
          // Versuche, Themen aus den Details zu extrahieren
          if (activity.details) {
            if (activity.details.main_topic) {
              mainTopic = activity.details.main_topic;
            }
            if (Array.isArray(activity.details.subtopics)) {
              subtopics = activity.details.subtopics;
            }
          }
          
          sessionMap.set(sessionId, {
            id: sessionId,
            mainTopic,
            timestamp: activity.timestamp,
            activities: [],
            primaryType: activity.activity_type,
            subtopics
          });
          
          debug(`Neue Session erstellt: ${sessionId}, Hauptthema: ${mainTopic}`);
        }
        
        // Aktivität zur Session hinzufügen
        const session = sessionMap.get(sessionId)!;
        session.activities.push(activity);
        
        // Upload-Aktivitäten haben höhere Priorität für primaryType
        if (activity.activity_type === 'upload') {
          session.primaryType = 'upload';
        }
        
        // Zähle Flashcards und Fragen
        if (activity.activity_type === 'flashcard') {
          session.flashcardCount = (session.flashcardCount || 0) + 1;
        } else if (activity.activity_type === 'question') {
          session.questionCount = (session.questionCount || 0) + 1;
        }
      });
      
      // Nach Datum sortieren (neueste zuerst)
      const sessionList = Array.from(sessionMap.values()).sort((a, b) => 
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      
      debug(`${sessionList.length} Sessions erstellt`);
      setSessions(sessionList);
    } catch (error) {
      debug("Fehler bei der Verarbeitung der Aktivitäten", error);
      setSessions([]);
    }
  }, [activities, debug]);

  // Initialer Ladevorgang
  useEffect(() => {
    if (user) {
      debug("Initialer Ladevorgang");
      loadActivities();
    }
  }, [user, loadActivities, debug]);

  // Datumsformatierung
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

  // Behandlung von Session-Klicks
  const handleSessionClick = async (session: SessionData) => {
    if (loadingSession) {
      debug("Eine andere Session wird bereits geladen");
      return;
    }
    
    debug(`Session ausgewählt: ${session.id}, Hauptthema: ${session.mainTopic}`);
    setLoadingSession(session.id);
    
    // Toast anzeigen
    const toastRef = toast({
      title: t('dashboard.loadingSession', 'Session wird geladen...'),
      description: session.mainTopic,
      duration: 10000 // 10 Sekunden
    });
    
    try {
      // Credits im Hintergrund aktualisieren
      refreshUserCredits().catch(e => debug("Fehler beim Aktualisieren der Credits", e));
      
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        debug("Kein Token gefunden");
        throw new Error("Nicht authentifiziert");
      }
      
      // Daten laden
      debug(`Lade Daten für Session ${session.id}`);
      const timestamp = Date.now();
      const url = `${API_URL}/api/v1/results/${session.id}?t=${timestamp}`;
      
      const response = await axiosInstance.get(url);
      
      debug("Antwort erhalten", {
        status: response.status,
        success: response.data?.success
      });
      
      if (!response.data?.success) {
        throw new Error(response.data?.message || "Fehler beim Laden der Daten");
      }
      
      const sessionData = response.data.data;
      if (!sessionData) {
        throw new Error("Keine Daten in der Antwort");
      }
      
      // Cleanup Toast
      toast({
        title: t('dashboard.loadingComplete', 'Daten geladen'),
        description: t('dashboard.loadingSuccess', 'Die Daten wurden erfolgreich geladen.'),
        duration: 2000
      });
      
      // Session-ID im localStorage speichern
      localStorage.setItem('current_session_id', session.id);
      
      // Callback oder Navigation
      if (onSessionSelect) {
        debug("Rufe onSessionSelect auf");
        onSessionSelect(
          session.id, 
          session.primaryType || 'upload', 
          session.mainTopic
        );
      } else {
        debug("Navigiere zur Startseite mit den geladenen Daten");
        
        // Statistische Daten
        const flashcardCount = sessionData.flashcards?.length || 0;
        const questionCount = sessionData.test_questions?.length || 0;
        
        debug(`Lade Daten: ${flashcardCount} Karteikarten, ${questionCount} Fragen`);
        
        navigate('/', {
          state: {
            sessionId: session.id,
            flashcards: sessionData.flashcards || [],
            questions: sessionData.test_questions || [],
            analysis: sessionData.analysis,
            forceReload: true
          },
        });
        
        toast({
          title: t('dashboard.analysisLoaded', 'Analyse geladen'),
          description: `${session.mainTopic}: ${flashcardCount} Karteikarten, ${questionCount} Fragen`,
        });
      }
      
      // Session-Historie aktualisieren
      updateSessionTimestamp(session).catch(e => 
        debug("Fehler beim Aktualisieren des Timestamps", e)
      );
      
    } catch (error: any) {
      debug("Fehler beim Laden der Session", error);
      
      // Toast aktualisieren
      toast({
        title: t('common.error'),
        description: error.message || t('dashboard.sessionLoadError', 'Fehler beim Laden der Session'),
        variant: "destructive"
      });
      
    } finally {
      setLoadingSession(null);
    }
  };

  // Aktualisierung des Session-Zeitstempels
  const updateSessionTimestamp = async (session: SessionData) => {
    if (!session.activities?.length) return;
    
    const activity = session.activities[0];
    debug(`Aktualisiere Timestamp für Aktivität: ${activity.id}`);
    
    const token = localStorage.getItem('exammaster_token');
    if (!token) return;
    
    try {
      await axios.put(`${API_URL}/api/v1/user-history/${activity.id}`, {}, { 
        headers: { Authorization: `Bearer ${token}` },
        withCredentials: true 
      });
      
      // Aktivitäten neu laden, um Historie zu aktualisieren
      loadActivities();
    } catch (error) {
      debug("Fehler beim Aktualisieren des Timestamps", error);
    }
  };

  // Generieren neuer Inhalte
  const generateNewContent = async (sessionId: string, contentType: 'flashcards' | 'questions' | 'topics') => {
    debug(`Generiere neue ${contentType} für Session ${sessionId}`);
    setLoadingSession(sessionId);
    
    try {
      const token = localStorage.getItem('exammaster_token');
      if (!token) throw new Error("Nicht authentifiziert");
      
      const response = await axios.post(
        `${API_URL}/api/v1/generate`, 
        { sessionId, contentType }, 
        { 
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true 
        }
      );
      
      if (response.data.success) {
        toast({
          title: t('dashboard.contentGenerated', 'Inhalte generiert'),
          description: t('dashboard.contentGeneratedDesc', 'Neue Inhalte wurden erfolgreich generiert.'),
        });
        
        // Historie neu laden und Session öffnen
        await loadActivities();
        const session = sessions.find(s => s.id === sessionId);
        if (session) {
          await handleSessionClick(session);
        }
      } else {
        throw new Error(response.data.message || `Fehler beim Generieren von ${contentType}`);
      }
    } catch (error: any) {
      debug(`Fehler beim Generieren von ${contentType}`, error);
      toast({
        title: t('common.error'),
        description: error.message || t('dashboard.contentGenerationError', 'Fehler bei der Generierung'),
        variant: "destructive",
      });
    } finally {
      setLoadingSession(null);
    }
  };
  
  // Verhindern, dass Dropdown-Klicks die Session öffnen
  const handleDropdownClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  // --------- DEBUG PANEL ---------
  const renderDebugPanel = () => {
    if (process.env.NODE_ENV !== 'development') return null;
    
    return (
      <div className="mb-4 p-4 border border-yellow-300 bg-yellow-50 dark:bg-yellow-900/20 rounded-md text-xs">
        <h4 className="font-bold mb-2 flex items-center">
          <AlertCircle className="h-4 w-4 mr-1" />
          Debug-Informationen
        </h4>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <p>User: {user ? 'Angemeldet' : 'Nicht angemeldet'}</p>
            <p>Activities: {activities.length}</p>
            <p>Sessions: {sessions.length}</p>
            <p>Loading: {loading ? 'Ja' : 'Nein'}</p>
            <p>Loading Session: {loadingSession || 'Keine'}</p>
          </div>
          <div className="overflow-hidden">
            <p className="truncate">Letzte Nachricht: {debugInfo.lastMessage}</p>
            <p className="truncate">Letzter Zeitstempel: {debugInfo.lastTimestamp}</p>
            <button 
              onClick={loadActivities}
              className="mt-2 px-2 py-1 bg-blue-500 text-white rounded text-xs"
            >
              Debug: Neu laden
            </button>
          </div>
        </div>
      </div>
    );
  };

  // --------- RENDER ---------
  return (
    <div className="py-6">
      {process.env.NODE_ENV === 'development' && renderDebugPanel()}
      
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">{t('dashboard.historySection.analyzedSessions', 'Analysierte Sessions')}</h3>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => loadActivities()}
          disabled={loading}
        >
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          {t('dashboard.historySection.refresh', 'Aktualisieren')}
        </Button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <div className="text-center py-10 border border-dashed rounded-lg">
          <div className="text-muted-foreground">
            {t('dashboard.historySection.noSessions', 'Keine analysierten Sessions gefunden.')}
          </div>
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
              >
                <Card 
                  className={`relative overflow-hidden p-4 hover:shadow-md transition-all duration-300
                           ${loadingSession === session.id ? 'opacity-70 pointer-events-none' : 'cursor-pointer'}`}
                  onClick={() => handleSessionClick(session)}
                >
                  {/* Loading Overlay */}
                  {loadingSession === session.id && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-sm z-20">
                      <div className="flex flex-col items-center gap-2">
                        <div className="h-8 w-8 rounded-full border-3 border-primary border-t-transparent animate-spin" />
                        <span className="text-xs text-muted-foreground animate-pulse">
                          {t('dashboard.loading', 'Wird geladen...')}
                        </span>
                      </div>
                    </div>
                  )}
                  
                  {/* Content */}
                  <div className="flex items-start">
                    {/* Icon */}
                    <div className={`p-2 rounded-md mr-3 ${
                      session.primaryType === 'question' ? 'bg-blue-100 dark:bg-blue-900' : 
                      session.primaryType === 'flashcard' ? 'bg-green-100 dark:bg-green-900' : 'bg-gray-100 dark:bg-gray-800'
                    }`}>
                      {session.primaryType === 'question' ? (
                        <HelpCircle className="h-5 w-5 text-blue-700 dark:text-blue-300" />
                      ) : session.primaryType === 'flashcard' ? (
                        <Layers className="h-5 w-5 text-green-700 dark:text-green-300" />
                      ) : (
                        <FileText className="h-5 w-5 text-gray-700 dark:text-gray-300" />
                      )}
                    </div>
                    
                    {/* Content */}
                    <div className="flex-1">
                      <div className="flex justify-between">
                        <h4 className="font-medium text-md line-clamp-1">{session.mainTopic}</h4>
                        
                        {/* Badges */}
                        <div className="flex gap-1">
                          {(session.flashcardCount || 0) > 0 && (
                            <span className="inline-flex items-center bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 
                                       px-2 py-0.5 rounded text-xs">
                              <Layers className="h-3 w-3 mr-1" />
                              {session.flashcardCount}
                            </span>
                          )}
                          {(session.questionCount || 0) > 0 && (
                            <span className="inline-flex items-center bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 
                                       px-2 py-0.5 rounded text-xs">
                              <HelpCircle className="h-3 w-3 mr-1" />
                              {session.questionCount}
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {/* Date */}
                      <p className="text-xs text-muted-foreground mt-1 mb-2">
                        <Clock className="h-3 w-3 inline mr-1" />
                        {formatDate(session.timestamp)}
                      </p>
                      
                      {/* Tags */}
                      {session.subtopics && session.subtopics.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {session.subtopics.slice(0, 3).map((subtopic, idx) => (
                            <span key={idx} 
                              className="inline-flex items-center px-2 py-0.5 rounded-full text-xs 
                                      bg-muted text-muted-foreground"
                            >
                              {subtopic}
                            </span>
                          ))}
                          {session.subtopics.length > 3 && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs 
                                           bg-muted text-muted-foreground">
                              +{session.subtopics.length - 3}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  
                  {/* Dropdown Menu */}
                  <div className="absolute top-2 right-2" onClick={handleDropdownClick}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                          <span className="sr-only">{t('dashboard.menu', 'Menü')}</span>
                          <svg width="15" height="15" viewBox="0 0 15 15" fill="currentColor">
                            <path d="M8.625 1.875C8.625 2.25968 8.32968 2.625 7.875 2.625C7.42032 2.625 7.125 2.25968 7.125 1.875C7.125 1.49032 7.42032 1.125 7.875 1.125C8.32968 1.125 8.625 1.49032 8.625 1.875ZM8.625 7.5C8.625 7.88468 8.32968 8.25 7.875 8.25C7.42032 8.25 7.125 7.88468 7.125 7.5C7.125 7.11532 7.42032 6.75 7.875 6.75C8.32968 6.75 8.625 7.11532 8.625 7.5ZM7.875 13.875C8.32968 13.875 8.625 13.5097 8.625 13.125C8.625 12.7403 8.32968 12.375 7.875 12.375C7.42032 12.375 7.125 12.7403 7.125 13.125C7.125 13.5097 7.42032 13.875 7.875 13.875Z"></path>
                          </svg>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-[180px]">
                        <DropdownMenuItem onClick={() => generateNewContent(session.id, 'flashcards')}>
                          <Layers className="mr-2 h-4 w-4" />
                          <span>{t('dashboard.generateFlashcards', 'Karteikarten generieren')}</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => generateNewContent(session.id, 'questions')}>
                          <HelpCircle className="mr-2 h-4 w-4" />
                          <span>{t('dashboard.generateQuestions', 'Fragen generieren')}</span>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
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

export default UserHistory;
