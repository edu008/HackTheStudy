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
import { Github, Loader2 } from "lucide-react";
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
    if (!user) return;

    const urlParams = new URLSearchParams(location.search);
    const sessionIdFromUrl = urlParams.get('session');
    const locationState = location.state as any;
    const sessionIdFromState = locationState?.sessionId;
    const sessionToLoad = sessionIdFromUrl || sessionIdFromState;

    if (sessionToLoad && sessionToLoad !== sessionId) {
      loadSessionData(sessionToLoad);
    }
  }, [user, location, sessionId]);

  useEffect(() => {
    const hash = window.location.hash;
    if (hash && user) {
      const id = hash.substring(1);
      const element = document.getElementById(id);
      if (element) {
        setTimeout(() => {
          element.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      }
    } else if (!hash) {
      window.scrollTo(0, 0);
    }
  }, [user, location.hash]);

  const loadSessionData = async (sessionIdToLoad: string) => {
    if (isLoadingSession) return;

    setIsLoadingSession(true);

    try {
      console.log('DEBUG: Loading session data for session ID:', sessionIdToLoad);
      const response = await axios.get<{ success: boolean, data: SessionData }>(
        `${API_URL}/api/v1/results/${sessionIdToLoad}`,
        { withCredentials: true }
      );

      if (response.data.success && response.data.data) {
        const sessionData = response.data.data;
        console.log('DEBUG: Loaded session data:', sessionData);

        setFlashcards(sessionData.flashcards || []);
        setQuestions(sessionData.test_questions || []);
        setSessionId(sessionIdToLoad);

        toast({
          title: "Analyse geladen",
          description: `Die Analyse "${sessionData.analysis.main_topic}" wurde erfolgreich geladen.`,
        });

        const hash = window.location.hash;
        navigate(hash, { replace: true });
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
    console.log('DEBUG: Index received upload success data:', data);
    setFlashcards(data.flashcards);
    setQuestions(data.questions);
    setSessionId(data.session_id);
    document.getElementById('flashcards')?.scrollIntoView({ behavior: 'smooth' });
  };

  const generateMoreFlashcardsMutation = useMutation({
    mutationFn: async () => {
      console.log('DEBUG: Requesting more flashcards from backend');
      const response = await axios.post<UploadResponse>(
        `${API_URL}/api/v1/generate-more-flashcards`,
        { session_id: sessionId, count: 5 }, // Hinzugefügt: count
        { headers: { "Content-Type": "application/json" }, withCredentials: true } // withCredentials hinzugefügt
      );
      console.log('DEBUG: Received more flashcards response:', response.data);
      return response.data;
    },
    onSuccess: (data) => {
      console.log('DEBUG: Adding new flashcards to state', data);
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
      const response = await axios.post<UploadResponse>(
        `${API_URL}/api/v1/generate-more-questions`,
        { session_id: sessionId, count: 5 }, // Hinzugefügt: count
        { headers: { "Content-Type": "application/json" }, withCredentials: true } // withCredentials hinzugefügt
      );
      console.log('DEBUG: Raw response from generate-more-questions:', response.data);
      return response.data;
    },
    onSuccess: (data) => {
      console.log('DEBUG: Adding new questions to state', data);
      
      // Extract questions from the response, handling different possible structures
      let newQuestionsArray = [];
      if (data.data && Array.isArray(data.data.questions)) {
        console.log('DEBUG: Found questions in data.data.questions');
        newQuestionsArray = data.data.questions;
      } else if (data.data && typeof data.data === 'object' && 'questions' in data.data) {
        console.log('DEBUG: Found questions in data.data.questions (object)');
        newQuestionsArray = data.data.questions;
      } else if (Array.isArray(data.questions)) {
        console.log('DEBUG: Found questions in data.questions');
        newQuestionsArray = data.questions;
      } else {
        console.warn('DEBUG: Could not find questions in response:', data);
        newQuestionsArray = [];
      }
      
      console.log('DEBUG: Extracted questions array:', newQuestionsArray);
      
      // Filter out invalid questions
      const validQuestionsArray = newQuestionsArray.filter(q => 
        q && q.text && !q.text.includes("Could not generate") && 
        q.options && Array.isArray(q.options) && q.options.length >= 2
      );
      
      console.log('DEBUG: Valid questions after filtering:', validQuestionsArray);
      
      // Add unique IDs and normalize correctAnswer field
      const newQuestionsWithUniqueIds = validQuestionsArray.map(q => ({
        ...q,
        id: uuidv4(),
        correctAnswer: q.correctAnswer !== undefined ? q.correctAnswer : (q as any).correct !== undefined ? (q as any).correct : 0
      }));
      
      console.log('DEBUG: Questions with unique IDs:', newQuestionsWithUniqueIds);
      
      // Filter out duplicates
      const existingTexts = new Set(questions.map(q => q.text.toLowerCase().trim()));
      const filteredNewQuestions = newQuestionsWithUniqueIds.filter(q => !existingTexts.has(q.text.toLowerCase().trim()));
      
      console.log('DEBUG: Final filtered questions:', filteredNewQuestions);
      
      if (filteredNewQuestions.length === 0) {
        toast({
          title: "Keine neuen Fragen",
          description: "Es konnten keine neuen Fragen generiert werden.",
          variant: "destructive",
        });
        return;
      }
      
      // Update state with new questions
      const updatedQuestions = [...questions, ...filteredNewQuestions];
      console.log('DEBUG: Setting questions state with:', updatedQuestions);
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

  const handleSignIn = async (provider: string) => {
    await signIn(provider);
  };

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
              <ExamUploader onUploadSuccess={handleUploadSuccess} />
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
