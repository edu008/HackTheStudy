import { useState, useEffect } from 'react';
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

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

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
  const [loading, setLoading] = useState(true);
  const [loadingSession, setLoadingSession] = useState<string | null>(null);
  const [mainTopic, setMainTopic] = useState<string>("");
  const [flashcards, setFlashcards] = useState<any[]>([]);
  const [questions, setQuestions] = useState<any[]>([]);
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user } = useAuth();

  useEffect(() => {
    if (!user) {
      toast({
        title: "Nicht authentifiziert",
        description: "Bitte melden Sie sich an, um Ihre Historie zu sehen.",
        variant: "destructive",
      });
      navigate('/login');
      return;
    }
    loadActivities();
  }, [user, navigate]);

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

  const loadActivities = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('exammaster_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      const response = await axios.get(`${API_URL}/api/v1/user-history`, { 
        headers,
        withCredentials: true 
      });
      
      if (response.data.success && Array.isArray(response.data.activities)) {
        setActivities(response.data.activities);
      } else {
        console.warn("⚠️ Keine Aktivitäten gefunden.");
        setActivities([]);
      }
    } catch (error) {
      console.error("❌ Fehler beim Abrufen der Aktivitäten:", error);
      toast({
        title: "Fehler",
        description: "Die Aktivitäten konnten nicht geladen werden.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('de-DE', { 
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
          title: "Inhalte generiert",
          description: `Neue ${contentType} wurden erfolgreich generiert.`,
        });
        
        // Lade die Aktivitäten neu, um die neuen Inhalte anzuzeigen
        await loadActivities();
        
        // Lade die Session mit den neuen Inhalten
        await handleSessionClick(sessions.find(s => s.id === sessionId)!);
      } else {
        throw new Error(`Fehler beim Generieren von ${contentType}`);
      }
    } catch (error) {
      console.error(`❌ Fehler beim Generieren von ${contentType}:`, error);
      toast({
        title: "Fehler",
        description: `Die ${contentType} konnten nicht generiert werden.`,
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
      title: "Neue Session",
      description: "Starte eine neue Session. Bitte lade deine Prüfungen hoch.",
    });
  };

  // Funktion zum Öffnen einer Session
  const handleSessionClick = async (session: SessionData) => {
    setLoadingSession(session.id);
    try {
      const token = localStorage.getItem('exammaster_token');
      const headers = token ? { 
        Authorization: `Bearer ${token}`,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
      } : {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
      };
      
      // Cache-busting Parameter hinzufügen, um sicherzustellen, dass wir frische Daten erhalten
      const timestamp = new Date().getTime();
      
      // Zuerst warten wir einen Moment, um sicherzustellen, dass der Server Zeit hatte,
      // die Daten vollständig zu verarbeiten (besonders wichtig bei gerade hochgeladenen Dateien)
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      const response = await axios.get(`${API_URL}/api/v1/results/${session.id}?nocache=${timestamp}`, {
        headers,
        withCredentials: true,
      });
      
      if (response.data.success) {
        const sessionData = response.data.data;
        const flashcardCount = sessionData.flashcards?.length || 0;
        const questionCount = sessionData.test_questions?.length || 0;
        
        console.log(`DEBUG: Loaded session data with ${flashcardCount} flashcards and ${questionCount} questions`);
        
        // Wenn die Sitzung noch verarbeitet wird und keine Karten/Fragen hat, warten wir nochmals
        if (sessionData.analysis.processing_status === "processing" && 
            flashcardCount === 0 && questionCount === 0) {
          
          toast({
            title: "Sitzung wird noch verarbeitet",
            description: "Die Daten werden noch verarbeitet. Bitte warten Sie einen Moment.",
          });
          
          // Warte 5 Sekunden und versuche es erneut
          await new Promise(resolve => setTimeout(resolve, 5000));
          
          // Erneuter Abruf mit neuem Timestamp
          const newTimestamp = new Date().getTime();
          const retryResponse = await axios.get(`${API_URL}/api/v1/results/${session.id}?nocache=${newTimestamp}`, {
            headers,
            withCredentials: true,
          });
          
          if (retryResponse.data.success) {
            const updatedSessionData = retryResponse.data.data;
            
            // Navigiere zur Hauptseite und übergebe die Daten
            navigate(`/`, {
              state: {
                sessionId: session.id,
                flashcards: updatedSessionData.flashcards || [],
                questions: updatedSessionData.test_questions || [],
                analysis: updatedSessionData.analysis,
                forceReload: true // Erzwinge ein Neuladen auch bei gleicher ID
              },
            });
            
            toast({
              title: "Analyse geladen",
              description: `Die Analyse "${session.mainTopic}" wurde erfolgreich geladen mit ${updatedSessionData.flashcards.length} Karten und ${updatedSessionData.test_questions.length} Fragen.`,
            });
            
            // Rest der Funktion überspringen
            return;
          }
        }
        
        // Standard-Ablauf, wenn alles in Ordnung ist
        navigate(`/`, {
          state: {
            sessionId: session.id,
            flashcards: sessionData.flashcards || [],
            questions: sessionData.test_questions || [],
            analysis: sessionData.analysis,
            forceReload: true // Erzwinge ein Neuladen auch bei gleicher ID
          },
        });
        
        toast({
          title: "Analyse geladen",
          description: `Die Analyse "${session.mainTopic}" wurde erfolgreich geladen mit ${flashcardCount} Karten und ${questionCount} Fragen.`,
        });

        // Aktualisiere den timestamp, um die Session nach vorne zu bewegen
        if (session.activities.length > 0) {
          const activity = session.activities[0];
          await axios.put(`${API_URL}/api/v1/user-history/${activity.id}`, {}, { 
            headers,
            withCredentials: true 
          });
          await loadActivities(); // Lade die Historie neu
        }
      } else {
        throw new Error("Keine Daten gefunden");
      }
    } catch (error) {
      console.error("❌ Fehler beim Laden der Session:", error);
      toast({
        title: "Fehler beim Laden",
        description: "Die Daten für diese Session konnten nicht geladen werden.",
        variant: "destructive",
      });
    } finally {
      setLoadingSession(null);
    }
  };
  
  // Verhindert, dass das Klicken auf die Dropdown-Menüs die Session öffnet
  const handleDropdownClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  useEffect(() => {
    loadActivities();
  }, []);

  return (
    <div className="py-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">Analysierte Sessions</h3>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={loadActivities} 
          disabled={loading}
        >
          <RefreshCw className="h-4 w-4 mr-1" />
          Aktualisieren
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
          <div>Keine analysierten Sessions gefunden.</div>
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
                          <div className="flex items-center gap-1" title="Flashcards">
                            <BookOpen className="h-4 w-4" />
                            <span className="text-xs">{session.flashcardCount}</span>
                          </div>
                        )}
                        {session.questionCount && session.questionCount > 0 && (
                          <div className="flex items-center gap-1" title="Testfragen">
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

export default UserHistory;
