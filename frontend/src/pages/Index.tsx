import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import { useMutation } from "@tanstack/react-query";
import { v4 as uuidv4 } from 'uuid';

// UI Components
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";

// Landing Page Components
import HeroSection from '@/components/landing/HeroSection';
import LoginSection from '@/components/landing/LoginSection';
import AboutSection from '@/components/landing/AboutSection';

// Main App Components
import ExamUploader from "@/components/ExamUploader";
import FlashcardGenerator from "@/components/FlashcardGenerator";
import TestSimulator from "@/components/TestSimulator";
import ConceptMapper from "@/components/ConceptMapper";
import { Loader2 } from "lucide-react";

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
  
  // App state for logged-in functionality
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  
  // Landing page navigation state
  const [currentView, setCurrentView] = useState<'hero' | 'about' | 'login'>('hero');
  const heroSectionRef = useRef<HTMLDivElement>(null);
  const aboutSectionRef = useRef<HTMLDivElement>(null);
  const loginSectionRef = useRef<HTMLDivElement>(null);

  // Scroll to the appropriate section when view changes
  useEffect(() => {
    if (currentView === 'login' && loginSectionRef.current) {
      loginSectionRef.current.scrollIntoView({ behavior: 'smooth' });
    } else if (currentView === 'about' && aboutSectionRef.current) {
      aboutSectionRef.current.scrollIntoView({ behavior: 'smooth' });
    } else if (currentView === 'hero' && heroSectionRef.current) {
      heroSectionRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentView]);

  // Load session data functionality
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

  // Check for session ID and state data from URL
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

  // Check for forced session reset
  useEffect(() => {
    // Prüfe, ob wir gerade von einem Reset-Redirect kommen
    const forceNewSession = sessionStorage.getItem('force_new_session');
    
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

  // Handle upload success
  const handleUploadSuccess = (data: UploadResponse) => {
    setFlashcards(data.flashcards || []);
    setQuestions(data.questions || []);
    setSessionId(data.session_id);
    document.getElementById('flashcards')?.scrollIntoView({ behavior: 'smooth' });
  };

  // Mutation to generate more flashcards
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

  // Mutation to generate more questions
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

  // Mutation to reset session and load new topics
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

  // Handle sign-in with provider
  const handleSignIn = async (provider: string) => {
    await signIn(provider);
  };

  // Handle going back to hero section
  const handleBackToHero = () => {
    setCurrentView('hero');
    if (heroSectionRef.current) {
      heroSectionRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center">
        <div className="animate-pulse text-lg">Loading...</div>
      </div>
    );
  }

  return (
    <>
      {!user ? (
        // Landing page layout without Navbar and Footer
        <div className="min-h-screen w-full flex flex-col bg-[#f0f7ff]">
          {/* Hero Section - Full height for initial view */}
          <section 
            ref={heroSectionRef}
            className={`min-h-screen flex items-center justify-center bg-[#f0f7ff] py-20 ${currentView !== 'hero' ? 'h-auto' : ''}`}
            id="hero-section"
          >
            <div className="w-full">
              <HeroSection 
                onStartClick={() => setCurrentView('login')}
                onLearnMoreClick={() => setCurrentView('about')}
              />
            </div>
          </section>
          
          {/* About Section */}
          <section 
            ref={aboutSectionRef} 
            className={`min-h-screen py-20 flex items-center bg-[#f0f7ff] ${currentView === 'about' ? 'animate-fade-in' : ''}`}
            id="about-section"
          >
            <div className="w-full">
              <AboutSection 
                onStartClick={() => setCurrentView('login')}
                onBackClick={handleBackToHero}
              />
            </div>
          </section>
          
          {/* Login Section */}
          <section 
            ref={loginSectionRef} 
            className={`min-h-screen py-20 flex items-center justify-center bg-[#f0f7ff] ${currentView === 'login' ? 'animate-fade-in' : ''}`}
            id="login-section"
          >
            <div className="w-full">
              <LoginSection 
                onBackClick={handleBackToHero}
                onSignIn={handleSignIn}
              />
            </div>
          </section>
        </div>
      ) : (
        // Logged-in user view with Navbar and Footer
        <div className="min-h-screen flex flex-col bg-[#f0f7ff]">
          <Navbar onLoginClick={() => setCurrentView('login')} />
          
          <main className="flex-1">
            {isLoadingSession && (
              <div className="fixed inset-0 bg-white/80 flex items-center justify-center z-50">
                <div className="bg-white p-6 rounded-lg shadow-lg flex flex-col items-center">
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
          </main>
          
          <Footer />
        </div>
      )}
    </>
  );
};

export default Index;

