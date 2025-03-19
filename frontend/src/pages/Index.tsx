import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import Navbar from "@/components/Navbar";
import ExamUploader from "@/components/ExamUploader";
import FlashcardGenerator from "@/components/FlashcardGenerator";
import TestSimulator from "@/components/TestSimulator";
import Footer from "@/components/Footer";
import { useMutation } from "@tanstack/react-query";
import axios from "axios";
import ConceptMapper from "@/components/ConceptMapper";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { FcGoogle } from "react-icons/fc";
import { Github, Loader2, BookOpen, Plus } from "lucide-react";
import { v4 as uuidv4 } from 'uuid';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

console.log('API_URL:', API_URL);

interface Flashcard {
  id: string;
  question: string;
  answer: string;
}

interface Question {
  id: string;
  text: string;
  options: string[];
  correctAnswer: number;
  explanation?: string;
}

interface UploadResponse {
  success: boolean;
  message: string;
  flashcards?: Flashcard[];
  questions?: Question[];
  session_id?: string;
  data?: {
    flashcards?: Flashcard[];
    questions?: Question[];
    test_questions?: Question[];
  };
}

interface SessionData {
  flashcards: Flashcard[];
  test_questions: Question[];
  analysis: {
    main_topic: string;
    subtopics: string[];
    content_type?: string;
    language?: string;
  };
}

const Index = () => {
  const { toast } = useToast();
  const { user, isLoading, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [isLoadingSession, setIsLoadingSession] = useState(false);

  useEffect(() => {
    // Erkennen, ob wir mit einem nocache-Parameter geladen wurden, was ein komplettes Reset signalisiert
    const urlParams = new URLSearchParams(location.search);
    const nocache = urlParams.get('nocache');
    
    if (nocache) {
      // Entferne alle URL-Parameter
      window.history.replaceState({}, '', window.location.pathname);
      
      // Zeige eine Erfolgsmeldung
      toast({
        title: "Neue Session gestartet",
        description: "Alle vorherigen Daten wurden gelöscht. Du kannst jetzt neue Dateien hochladen.",
      });
      
      return;
    }
    
    if (!user) return;

    // Prüfe, ob eine Session aus dem URL-Parameter geladen werden soll
    const sessionIdFromUrl = urlParams.get('session');
    const sessionDataFromState = location.state as {
      sessionId?: string;
      flashcards?: Flashcard[];
      questions?: Question[];
      analysis?: { main_topic: string; subtopics: string[] };
      forceReload?: boolean;
    };

    // Wenn URL-Parameter und Session-ID unterschiedlich sind, priorisiere URL-Parameter
    if (sessionIdFromUrl && sessionIdFromUrl !== sessionId) {
      loadSessionData(sessionIdFromUrl);
      return;
    }

    // Wenn State-Daten vorhanden sind, nutze diese
    if (sessionDataFromState?.sessionId) {
      const stateSessionId = sessionDataFromState.sessionId;
      
      // Wenn sich die Session-ID geändert hat oder wir eine neue Session geladen haben
      // oder wenn ein forceReload Flag gesetzt wurde
      if (stateSessionId !== sessionId || sessionDataFromState.forceReload) {
        setIsLoadingSession(true);
        
        // Wenn Daten im State vorhanden sind, verwende diese
        if (sessionDataFromState.flashcards || sessionDataFromState.questions) {
          // Immer die neuen Daten verwenden, alte verwerfen
          setFlashcards(sessionDataFromState.flashcards || []);
          setQuestions(sessionDataFromState.questions || []);
          setSessionId(stateSessionId);
          
          const flashcardCount = sessionDataFromState.flashcards?.length || 0;
          const questionCount = sessionDataFromState.questions?.length || 0;
          
          toast({
            title: "Analyse geladen",
            description: `Die Analyse "${sessionDataFromState.analysis?.main_topic || 'Unbenanntes Thema'}" wurde erfolgreich geladen mit ${flashcardCount} Karten und ${questionCount} Fragen.`,
          });
          setIsLoadingSession(false);
        } else {
          // Wenn keine Daten im State, lade sie vom Server
          loadSessionData(stateSessionId);
        }
      }
      return;
    }

    // Wenn keine spezifischen Parameter vorhanden sind, aber wir eine sessionId haben,
    // leere den Zustand (dies passiert typischerweise bei Neuladen der Seite)
    if (!sessionIdFromUrl && !sessionDataFromState?.sessionId && sessionId) {
      setSessionId(undefined);
      setFlashcards([]);
      setQuestions([]);
    }
  }, [user, location.search, location.state]);

  const loadSessionData = async (sessionIdToLoad: string) => {
    if (isLoadingSession) return;

    setIsLoadingSession(true);
    try {
      // Cache-busting Parameter hinzufügen, um sicherzustellen, dass wir frische Daten erhalten
      const timestamp = new Date().getTime();
      const response = await axios.get<{ success: boolean; data: SessionData }>(
        `${API_URL}/api/v1/results/${sessionIdToLoad}?nocache=${timestamp}`,
        { 
          withCredentials: true,
          headers: {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
          }
        }
      );
      
      if (response.data.success && response.data.data) {
        const sessionData = response.data.data;
        console.log('DEBUG: Loaded session data:', sessionData);
        
        // Immer die neuen Daten verwenden, unabhängig von früheren Zuständen
        setFlashcards(sessionData.flashcards || []);
        setQuestions(sessionData.test_questions || []);
        setSessionId(sessionIdToLoad);
        
        toast({
          title: "Analyse geladen",
          description: `Die Analyse "${sessionData.analysis.main_topic}" wurde erfolgreich geladen mit ${sessionData.flashcards.length} Karteikarten und ${sessionData.test_questions.length} Fragen.`,
        });
      } else {
        throw new Error("Keine gültigen Daten für diese Session gefunden");
      }
    } catch (error) {
      console.error('DEBUG: Error loading session data:', error);
      toast({
        title: "Fehler beim Laden",
        description: "Die Daten für diese Session konnten nicht geladen werden.",
        variant: "destructive",
      });
    } finally {
      setIsLoadingSession(false);
    }
  };

  const handleUploadSuccess = (data: UploadResponse) => {
    setFlashcards(data.flashcards || []);
    setQuestions(data.questions || []);
    setSessionId(data.session_id);
    document.getElementById('flashcards')?.scrollIntoView({ behavior: 'smooth' });
  };

  const generateMoreFlashcardsMutation = useMutation({
    mutationFn: async () => {
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        throw new Error('Nicht eingeloggt. Bitte melde dich an, um diese Funktion zu nutzen.');
      }
      
      const response = await axios.post<UploadResponse>(
        `${API_URL}/api/v1/generate-more-flashcards`,
        { session_id: sessionId, count: 5 },
        { 
          headers: { 
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          }, 
          withCredentials: true 
        }
      );
      return response.data;
    },
    onSuccess: (data) => {
      const newFlashcardsArray = data.data?.flashcards || data.flashcards || [];
      const newFlashcardsWithUniqueIds = newFlashcardsArray.map(f => ({
        ...f,
        id: uuidv4()
      }));
      setFlashcards([...flashcards, ...newFlashcardsWithUniqueIds]);
      toast({
        title: "Neue Karteikarten generiert",
        description: `${newFlashcardsWithUniqueIds.length} neue Karteikarten wurden erstellt.`,
      });
    },
    onError: () => {
      toast({
        title: "Fehler",
        description: "Beim Generieren neuer Karteikarten ist ein Fehler aufgetreten.",
        variant: "destructive",
      });
    }
  });

  const generateMoreQuestionsMutation = useMutation({
    mutationFn: async () => {
      console.log('DEBUG: Requesting more test questions from backend');
      if (!sessionId) {
        throw new Error('Keine Session-ID vorhanden. Bitte lade zuerst eine Prüfung hoch.');
      }
      
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        throw new Error('Nicht eingeloggt. Bitte melde dich an, um diese Funktion zu nutzen.');
      }
      
      const response = await axios.post<UploadResponse>(
        `${API_URL}/api/v1/generate-more-questions`,
        { session_id: sessionId, count: 5 },
        { 
          headers: { 
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          }, 
          withCredentials: true 
        }
      );
      return response.data;
    },
    onSuccess: (data) => {
      console.log('DEBUG: Adding new questions to state', data);
      
      let newQuestionsArray = [];
      if (data.data && Array.isArray(data.data.questions)) {
        newQuestionsArray = data.data.questions;
      } else if (data.data && typeof data.data === 'object' && 'questions' in data.data) {
        newQuestionsArray = data.data.questions;
      } else if (Array.isArray(data.questions)) {
        newQuestionsArray = data.questions;
      } else {
        console.warn('DEBUG: Could not find questions in response:', data);
        newQuestionsArray = [];
      }
      
      const validQuestionsArray = newQuestionsArray.filter(q => 
        q && q.text && !q.text.includes("Could not generate") && 
        q.options && Array.isArray(q.options) && q.options.length >= 2
      );
      
      const newQuestionsWithUniqueIds = validQuestionsArray.map(q => ({
        ...q,
        id: uuidv4(),
        correctAnswer: q.correctAnswer !== undefined ? q.correctAnswer : (q as any).correct !== undefined ? (q as any).correct : 0
      }));
      
      const existingTexts = new Set(questions.map(q => q.text.toLowerCase().trim()));
      const filteredNewQuestions = newQuestionsWithUniqueIds.filter(q => !existingTexts.has(q.text.toLowerCase().trim()));
      
      if (filteredNewQuestions.length === 0) {
        toast({
          title: "Keine neuen Fragen",
          description: "Es konnten keine neuen Fragen generiert werden.",
          variant: "destructive",
        });
        return;
      }
      
      const updatedQuestions = [...questions, ...filteredNewQuestions];
      setQuestions(updatedQuestions);
      toast({
        title: "Neue Testfragen generiert",
        description: `${filteredNewQuestions.length} neue Testfragen wurden erstellt.`,
      });
    },
    onError: (error: any) => {
      toast({
        title: "Fehler",
        description: error.message || "Beim Generieren neuer Testfragen ist ein Fehler aufgetreten.",
        variant: "destructive",
      });
    }
  });

  // Mutation zum Zurücksetzen der Session und Laden neuer Themen
  const loadTopicsMutation = useMutation({
    mutationFn: async () => {
      // Wir generieren eine temporäre ID für einen Redirect
      const redirectId = uuidv4();
      
      // Setze einen temporären State im sessionStorage, um zu signalisieren, dass wir alles neu laden wollen
      sessionStorage.setItem('force_new_session', 'true');
      sessionStorage.setItem('redirect_time', Date.now().toString());
      
      // Navigiere zu einer sicheren Zwischen-URL ohne Sessions und erzwinge einen harten Refresh
      window.location.href = `${window.location.pathname}?reset=${redirectId}`;
      
      // Rückgabewert wird nicht verwendet, da wir die Seite neuladen
      return { success: true };
    },
    onError: (error: any) => {
      toast({
        title: "Fehler",
        description: error.message || "Beim Zurücksetzen der Session ist ein Fehler aufgetreten.",
        variant: "destructive",
      });
    }
  });

  const handleSignIn = async (provider: string) => {
    await signIn(provider);
  };

  // Prüfe beim Laden der Seite, ob ein Reset erzwungen werden soll
  useEffect(() => {
    // Prüfe, ob wir gerade von einem Reset-Redirect kommen
    const forceNewSession = sessionStorage.getItem('force_new_session');
    const redirectTime = sessionStorage.getItem('redirect_time');
    
    if (forceNewSession === 'true') {
      // Lösche die Reset-Flags
      sessionStorage.removeItem('force_new_session');
      sessionStorage.removeItem('redirect_time');
      
      // Lösche alle Session-bezogenen Daten
      localStorage.removeItem('current_session_id');
      localStorage.removeItem('session_id');
      localStorage.removeItem('last_session_id');
      
      // Setze den lokalen Zustand zurück
      setSessionId(undefined);
      setFlashcards([]);
      setQuestions([]);
      
      // Entferne alle URL-Parameter für ein sauberes Neuladen
      if (window.location.search) {
        window.history.replaceState({}, '', window.location.pathname);
        
        // Nach kurzer Verzögerung (um React-Rendering abzuwarten) einen Toast anzeigen
        setTimeout(() => {
          toast({
            title: "Neue Session gestartet",
            description: "Die alte Session wurde vollständig entfernt und eine neue Session ist bereit.",
          });
        }, 500);
      }
    }
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center">
        <div className="animate-pulse text-lg">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1">
        {!user ? (
          <div className="container mx-auto px-4 py-16">
            <div className="text-center mb-16">
              <h1 className="text-4xl font-bold mb-4">Willkommen bei HackTheStudy</h1>
              <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
                Die intelligente Plattform für Studenten, um Prüfungen zu analysieren, 
                Karteikarten zu erstellen und sich optimal auf Tests vorzubereiten.
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
              <Card>
                <CardHeader>
                  <CardTitle>Prüfungen analysieren</CardTitle>
                  <CardDescription>
                    Lade deine Prüfungsunterlagen hoch und erhalte eine detaillierte Analyse.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p>Unsere KI analysiert deine Prüfungsunterlagen und identifiziert die wichtigsten Konzepte und Themen.</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Karteikarten erstellen</CardTitle>
                  <CardDescription>
                    Generiere automatisch Karteikarten aus deinen Unterlagen.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p>Erstelle effektive Lernmaterialien mit nur einem Klick und optimiere deine Lernzeit.</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Testsimulation</CardTitle>
                  <CardDescription>
                    Bereite dich mit realistischen Testfragen auf deine Prüfungen vor.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p>Übe mit automatisch generierten Testfragen, die auf deinen Unterlagen basieren.</p>
                </CardContent>
              </Card>
            </div>
            <div className="max-w-md mx-auto">
              <Card>
                <CardHeader className="text-center">
                  <CardTitle>Jetzt loslegen</CardTitle>
                  <CardDescription>
                    Melde dich an, um alle Funktionen zu nutzen
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Button variant="outline" className="w-full" onClick={() => handleSignIn('google')}>
                    <FcGoogle className="mr-2 h-4 w-4" />
                    Mit Google anmelden
                  </Button>
                  <Button variant="outline" className="w-full" onClick={() => handleSignIn('github')}>
                    <Github className="mr-2 h-4 w-4" />
                    Mit GitHub anmelden
                  </Button>
                  <Button variant="default" className="w-full" onClick={() => handleSignIn('mock')}>
                    Demo Login (ohne OAuth)
                  </Button>
                  <p className="text-xs text-center text-muted-foreground mt-2">
                    Hinweis: Für die echte OAuth-Authentifizierung muss der Backend-Server laufen.
                  </p>
                </CardContent>
                <CardFooter className="flex justify-center">
                  <p className="text-sm text-muted-foreground">
                    Neues Konto wird automatisch erstellt
                  </p>
                </CardFooter>
              </Card>
            </div>
          </div>
        ) : (
          <>
            {isLoadingSession && (
              <div className="fixed inset-0 bg-background/80 flex items-center justify-center z-50">
                <div className="bg-card p-6 rounded-lg shadow-lg flex flex-col items-center">
                  <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                  <p className="text-lg font-medium">Lade Analyse...</p>
                </div>
              </div>
            )}
            <section id="exam-uploader">
              <ExamUploader 
                onUploadSuccess={handleUploadSuccess} 
                sessionId={sessionId}
                loadTopicsMutation={loadTopicsMutation}
                onResetSession={() => {
                  // Setze den Session-Zustand in der übergeordneten Komponente zurück
                  setSessionId(undefined);
                  setFlashcards([]);
                  setQuestions([]);
                  
                  // API-Aufruf zum Zurücksetzen der Session auf dem Server
                  if (sessionId) {
                    try {
                      const token = localStorage.getItem('exammaster_token');
                      axios.delete(`${API_URL}/api/v1/session/${sessionId}`, {
                        headers: {
                          "Authorization": token ? `Bearer ${token}` : '',
                        },
                        withCredentials: true,
                      }).catch(error => {
                        console.error('Failed to delete session on server:', error);
                      });
                    } catch (error) {
                      console.error('Error deleting session:', error);
                    }
                  }
                  
                  // Explizit eine neue Session durch loadTopicsMutation starten
                  setTimeout(() => {
                    loadTopicsMutation.mutate();
                  }, 500);
                  
                  // Entferne die Session-ID aus der URL, falls vorhanden
                  const url = new URL(window.location.href);
                  if (url.searchParams.has('session')) {
                    url.searchParams.delete('session');
                    window.history.replaceState({}, '', url.toString());
                  }
                  
                  // Zeige eine Benachrichtigung
                  toast({
                    title: "Neue Session gestartet",
                    description: "Die alte Session wurde entfernt und eine neue Session wird erstellt.",
                  });
                }}
              />
            </section>
            <section id="flashcards">
              <FlashcardGenerator
                flashcards={flashcards}
                onGenerateMore={() => generateMoreFlashcardsMutation.mutate()}
                isGenerating={generateMoreFlashcardsMutation.isPending}
              />
            </section>
            <section id="test-simulator">
              <TestSimulator
                questions={questions}
                onGenerateMore={() => generateMoreQuestionsMutation.mutate()}
                isGenerating={generateMoreQuestionsMutation.isPending}
              />
            </section>
            <section id="concept-mapper">
              <ConceptMapper sessionId={sessionId} />
            </section>
          </>
        )}
      </main>
      <Footer />
    </div>
  );
};

export default Index;

