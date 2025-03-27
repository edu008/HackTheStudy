import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import { useMutation } from "@tanstack/react-query";
import { v4 as uuidv4 } from 'uuid';
import { Button } from "@/components/ui/button";
import { useTranslation } from 'react-i18next';

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
  correct?: number;
  explanation?: string;
}

interface UploadResponse {
  success: boolean;
  message: string;
  flashcards?: Flashcard[];
  questions?: Question[];
  session_id?: string;
  credits_available?: number;
  data?: {
    flashcards?: Flashcard[];
    questions?: Question[];
    test_questions?: Question[];
  };
  token_info?: {
    input_tokens: number;
    output_tokens: number;
    cost: number;
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
    files?: Array<any>;
    processing_status?: string;
  };
  session_id: string;
  topics?: {
    main_topic: {
      id: string;
      name: string;
    };
    subtopics: Array<{
      id: string;
      name: string;
    }>;
  };
  connections?: Array<{
    id: string;
    source_id: string;
    target_id: string;
    label: string;
  }>;
  concept_map?: {
    nodes: Array<any>;
    edges: Array<any>;
    topics?: any;
  };
}

const Index = () => {
  const { toast } = useToast();
  const { user, isLoading, signIn, refreshUserCredits } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  
  // App state for logged-in functionality
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [conceptMapData, setConceptMapData] = useState<{
    topics: SessionData['topics'];
    connections: SessionData['connections'];
  } | null>(null);
  
  // Token-Tracking-Zustände hinzufügen
  const [tokenInfoFlashcards, setTokenInfoFlashcards] = useState<{
    inputTokens: number;
    outputTokens: number;
    cost: number;
  } | undefined>(undefined);
  
  const [tokenInfoQuestions, setTokenInfoQuestions] = useState<{
    inputTokens: number;
    outputTokens: number;
    cost: number;
  } | undefined>(undefined);
  
  // Landing page navigation state
  const [currentView, setCurrentView] = useState<'hero' | 'about' | 'login' | 'test-simulator'>('hero');
  const heroSectionRef = useRef<HTMLDivElement>(null);
  const aboutSectionRef = useRef<HTMLDivElement>(null);
  const loginSectionRef = useRef<HTMLDivElement>(null);

  // Neuen State-Eintrag für 402-Fehlerstatus hinzufügen
  const [insufficientCredits, setInsufficientCredits] = useState<{
    area: 'flashcards' | 'questions';
    creditsRequired: number;
    creditsAvailable: number;
  } | null>(null);

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
      const token = localStorage.getItem('exammaster_token');
      const response = await axios.get<{ success: boolean; data: SessionData }>(
        `${API_URL}/api/v1/results/${sessionIdToLoad}?nocache=${timestamp}`,
        { 
          withCredentials: true,
          headers: {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Authorization': token ? `Bearer ${token}` : ''
          }
        }
      );
      
      if (response.data.success && response.data.data) {
        const sessionData = response.data.data;
        console.log('DEBUG: Successfully loaded session data:', sessionData);
        
        // Immer die neuen Daten verwenden, unabhängig von früheren Zuständen
        setFlashcards(sessionData.flashcards || []);
        setQuestions(sessionData.test_questions || []);
        setSessionId(sessionIdToLoad);
        
        // Concept Map-Daten setzen, falls vorhanden
        if (sessionData.concept_map) {
          // Wir haben direkt concept_map-Daten
          setConceptMapData({
            topics: sessionData.concept_map.topics || sessionData.topics,
            connections: sessionData.concept_map.edges || sessionData.connections || []
          });
        } else if (sessionData.topics || sessionData.connections) {
          // Falls keine concept_map-Daten, aber topics/connections vorhanden sind
          setConceptMapData({
            topics: sessionData.topics,
            connections: sessionData.connections
          });
        } else {
          // Falls keine Concept Map-Daten vorhanden sind, versuchen wir diese getrennt zu laden
          try {
            const token = localStorage.getItem('exammaster_token');
            const topicsResponse = await fetch(`${API_URL}/api/v1/topics/${sessionIdToLoad}`, {
              headers: {
                'Authorization': token ? `Bearer ${token}` : ''
              }
            });
            
            if (topicsResponse.ok) {
              const topicsData = await topicsResponse.json();
              
              if (topicsData.success) {
                setConceptMapData({
                  topics: topicsData.topics,
                  connections: topicsData.connections || []
                });
                console.log('DEBUG: Loaded concept map data separately:', topicsData);
              }
            }
          } catch (error) {
            console.error('DEBUG: Error loading concept map data separately:', error);
            // Fehler beim Laden der Concept Map-Daten sind nicht kritisch und werden nur geloggt
          }
        }
        
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
    // Setze zunächst die grundlegenden Daten aus dem Upload
    setFlashcards(data.flashcards || []);
    setQuestions(data.questions || []);
    setSessionId(data.session_id);
    
    // Die vollständigen Daten (einschließlich ConceptMap) wurden bereits in der
    // ExamUploader-Komponente geladen, bevor diese Funktion aufgerufen wurde
    
    // Hier können wir nur noch zusätzliche UI-Aktionen ausführen
    console.log("Upload und Analyseprozess erfolgreich abgeschlossen für Session:", data.session_id);
    
    // Scrolle zu den Flashcards
    document.getElementById('flashcards')?.scrollIntoView({ behavior: 'smooth' });
  };

  // Add code to save session ID to localStorage whenever it changes
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('current_session_id', sessionId);
      console.log('DEBUG: Saved sessionId to localStorage:', sessionId);
    }
  }, [sessionId]);

  // Zurücksetzen des insufficientCredits-Status, wenn sich die Credits des Benutzers ändern
  useEffect(() => {
    if (user?.credits && insufficientCredits) {
      // Wenn der Benutzer nun mehr Credits hat als erforderlich, setze den Status zurück
      if (user.credits >= insufficientCredits.creditsRequired) {
        setInsufficientCredits(null);
        toast({
          title: "Credits aufgeladen",
          description: "Du hast nun genügend Credits, um fortzufahren.",
        });
      }
    }
  }, [user?.credits, insufficientCredits]);

  // Function to get the current session ID from state or localStorage
  const getCurrentSessionId = (): string | undefined => {
    if (sessionId) {
      return sessionId;
    }
    
    const storedSessionId = localStorage.getItem('current_session_id');
    if (storedSessionId) {
      console.log('DEBUG: Using stored sessionId from localStorage:', storedSessionId);
      setSessionId(storedSessionId);
      return storedSessionId;
    }
    
    return undefined;
  };

  // Mutation to generate more flashcards
  const generateMoreFlashcardsMutation = useMutation({
    mutationFn: async () => {
      const currentSessionId = getCurrentSessionId();
      console.log('DEBUG: Using session ID for flashcards:', currentSessionId);
      
      if (!currentSessionId) {
        throw new Error('Keine Session-ID vorhanden. Bitte lade zuerst eine Prüfung hoch.');
      }
      
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        throw new Error('Nicht eingeloggt. Bitte melde dich an, um diese Funktion zu nutzen.');
      }
      
      const response = await axios.post<UploadResponse>(
        `${API_URL}/api/v1/generate-more-flashcards`,
        { session_id: currentSessionId, count: 5 },
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
      console.log("FLASHCARDS API SUCCESS RESPONSE:", data);
      const newFlashcardsArray = data.data?.flashcards || data.flashcards || [];
      console.log("New flashcards array:", newFlashcardsArray);
      
      // Token-Tracking-Informationen aktualisieren, falls vorhanden
      if (data.token_info) {
        setTokenInfoFlashcards({
          inputTokens: data.token_info.input_tokens,
          outputTokens: data.token_info.output_tokens,
          cost: data.token_info.cost
        });
        console.log("Token usage updated for flashcards:", data.token_info);
      }
      
      if (!newFlashcardsArray || newFlashcardsArray.length === 0) {
        console.error("No flashcards found in response data");
        toast({
          title: "Keine Karteikarten erhalten",
          description: "Es wurden keine neuen Karteikarten vom Server empfangen.",
          variant: "destructive",
        });
        return;
      }
      
      const newFlashcardsWithUniqueIds = newFlashcardsArray.map(f => ({
        ...f,
        id: uuidv4()
      }));
      
      // State-Update mit Callback für Debugging
      setFlashcards(prevFlashcards => {
        const updatedFlashcards = [...prevFlashcards, ...newFlashcardsWithUniqueIds];
        console.log(`Flashcards updated: ${prevFlashcards.length} -> ${updatedFlashcards.length}`);
        return updatedFlashcards;
      });
      
      // Aktualisiere die Benutzer-Credits, wenn sie in der Antwort enthalten sind
      if (data.credits_available !== undefined && user) {
        // Aktualisiere den lokalen User im localStorage
        const storedUser = localStorage.getItem('exammaster_user');
        if (storedUser) {
          try {
            const parsedUser = JSON.parse(storedUser);
            parsedUser.credits = data.credits_available;
            localStorage.setItem('exammaster_user', JSON.stringify(parsedUser));
            
            // Aktualisiere den Benutzer im Auth-Kontext
            refreshUserCredits();
            
            // Aktualisiere den Benutzer im lokalen State
            user.credits = data.credits_available;
          } catch (error) {
            console.error('Error updating user credits:', error);
          }
        }
      }
      
      toast({
        title: "Neue Karteikarten generiert",
        description: `${newFlashcardsWithUniqueIds.length} neue Karteikarten wurden erstellt.`,
      });
      
      // Nachdem wir neue Flashcards hinzugefügt haben, laden wir die aktuelle Session neu,
      // um sicherzustellen, dass alle Daten konsistent sind
      const sessionIdToReload = getCurrentSessionId();
      if (sessionIdToReload) {
        console.log("Reloading session data after generating flashcards:", sessionIdToReload);
        
        // Kurze Verzögerung, damit die Datenbank Zeit hat, die neuen Flashcards zu speichern
        setTimeout(() => {
          loadSessionData(sessionIdToReload);
        }, 500);
      }
    },
    onError: (error: any) => {
      // Spezielle Behandlung für 402 Payment Required (nicht genügend Credits)
      if (error.response?.status === 402) {
        const errorData = error.response.data?.error || {};
        const message = errorData.message || "Nicht genügend Credits für diese Aktion.";
        const creditsRequired = errorData.credits_required || 0;
        const creditsAvailable = errorData.credits_available || 0;
        
        // Aktualisiere die Benutzer-Credits in der UI, falls verfügbar
        if (user && creditsAvailable !== undefined && user.credits !== creditsAvailable) {
          // Aktualisiere den lokalen User im localStorage
          const storedUser = localStorage.getItem('exammaster_user');
          if (storedUser) {
            try {
              const parsedUser = JSON.parse(storedUser);
              parsedUser.credits = creditsAvailable;
              localStorage.setItem('exammaster_user', JSON.stringify(parsedUser));
              
              // Aktualisiere den Benutzer im Auth-Kontext
              refreshUserCredits();
              
              // Aktualisiere den Benutzer im lokalen State
              user.credits = creditsAvailable;
            } catch (error) {
              console.error('Error updating user credits:', error);
            }
          }
        }
        
        toast({
          title: "Credits nicht ausreichend",
          description: `${message} Benötigt: ${creditsRequired}, Verfügbar: ${creditsAvailable}`,
          variant: "destructive",
          duration: 8000,
        });
        
        // Setze den Status für den Kauf-Button
        setInsufficientCredits({
          area: 'flashcards',
          creditsRequired,
          creditsAvailable
        });
        
        return;
      }
      
      // Standard-Fehlerbehandlung für andere Fehler
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
      const currentSessionId = getCurrentSessionId();
      console.log('DEBUG: Using session ID for questions:', currentSessionId);
      
      if (!currentSessionId) {
        throw new Error('Keine Session-ID vorhanden. Bitte lade zuerst eine Prüfung hoch.');
      }
      
      const token = localStorage.getItem('exammaster_token');
      if (!token) {
        throw new Error('Nicht eingeloggt. Bitte melde dich an, um diese Funktion zu nutzen.');
      }
      
      // Füge einen Timestamp hinzu, um Cache-Probleme zu vermeiden
      const timestamp = new Date().getTime();
      
      const response = await axios.post<UploadResponse>(
        `${API_URL}/api/v1/generate-more-questions?t=${timestamp}`,
        { 
          session_id: currentSessionId, 
          count: 3,
          timestamp: timestamp // Zusätzlich im Body für Server
        },
        { 
          headers: { 
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
          }, 
          withCredentials: true 
        }
      );
      return response.data;
    },
    onSuccess: (data) => {
      console.log("QUESTIONS API SUCCESS RESPONSE:", data);
      const newQuestionsArray = data.data?.questions || data.questions || [];
      console.log("New questions array:", newQuestionsArray);
      
      // Token-Tracking-Informationen aktualisieren, falls vorhanden
      if (data.token_info) {
        setTokenInfoQuestions({
          inputTokens: data.token_info.input_tokens,
          outputTokens: data.token_info.output_tokens,
          cost: data.token_info.cost
        });
        console.log("Token usage updated for questions:", data.token_info);
      }
      
      if (!newQuestionsArray || newQuestionsArray.length === 0) {
        console.error("No questions found in response data");
        toast({
          title: "Keine Testfragen erhalten",
          description: "Es wurden keine neuen Testfragen vom Server empfangen.",
          variant: "destructive",
        });
        return;
      }
      
      const newQuestionsWithUniqueIds = newQuestionsArray.map(q => ({
        ...q,
        id: uuidv4(),
        // Sicherstellen, dass alle notwendigen Felder für die Frage-Komponente vorhanden sind
        text: q.text,
        options: q.options || [],
        correctAnswer: q.correct,
        explanation: q.explanation || ''
      }));
      
      // State-Update mit Callback für Debugging
      setQuestions(prevQuestions => {
        const updatedQuestions = [...prevQuestions, ...newQuestionsWithUniqueIds];
        console.log(`Questions updated: ${prevQuestions.length} -> ${updatedQuestions.length}`);
        return updatedQuestions;
      });
      
      // Aktualisiere die Benutzer-Credits, wenn sie in der Antwort enthalten sind
      if (data.credits_available !== undefined && user) {
        // Aktualisiere den lokalen User im localStorage
        const storedUser = localStorage.getItem('exammaster_user');
        if (storedUser) {
          try {
            const parsedUser = JSON.parse(storedUser);
            parsedUser.credits = data.credits_available;
            localStorage.setItem('exammaster_user', JSON.stringify(parsedUser));
            
            // Aktualisiere den Benutzer im Auth-Kontext
            refreshUserCredits();
            
            // Aktualisiere den Benutzer im lokalen State
            user.credits = data.credits_available;
          } catch (error) {
            console.error('Error updating user credits:', error);
          }
        }
      }
      
      toast({
        title: "Neue Testfragen generiert",
        description: `${newQuestionsWithUniqueIds.length} neue Testfragen wurden erstellt.`,
      });
      
      // Nachdem wir neue Testfragen hinzugefügt haben, laden wir die aktuelle Session neu,
      // um sicherzustellen, dass alle Daten konsistent sind
      const sessionIdToReload = getCurrentSessionId();
      if (sessionIdToReload) {
        console.log("Reloading session data after generating questions:", sessionIdToReload);
        
        // Kurze Verzögerung, damit die Datenbank Zeit hat, die neuen Testfragen zu speichern
        setTimeout(() => {
          loadSessionData(sessionIdToReload);
        }, 500);
      }
    },
    onError: (error: any) => {
      // Spezielle Behandlung für 402 Payment Required (nicht genügend Credits)
      if (error.response?.status === 402) {
        const errorData = error.response.data?.error || {};
        const message = errorData.message || "Nicht genügend Credits für diese Aktion.";
        const creditsRequired = errorData.credits_required || 0;
        const creditsAvailable = errorData.credits_available || 0;
        
        // Aktualisiere die Benutzer-Credits in der UI, falls verfügbar
        if (user && creditsAvailable !== undefined && user.credits !== creditsAvailable) {
          // Aktualisiere den lokalen User im localStorage
          const storedUser = localStorage.getItem('exammaster_user');
          if (storedUser) {
            try {
              const parsedUser = JSON.parse(storedUser);
              parsedUser.credits = creditsAvailable;
              localStorage.setItem('exammaster_user', JSON.stringify(parsedUser));
              
              // Aktualisiere den Benutzer im Auth-Kontext
              refreshUserCredits();
              
              // Aktualisiere den Benutzer im lokalen State
              user.credits = creditsAvailable;
            } catch (error) {
              console.error('Error updating user credits:', error);
            }
          }
        }
        
        toast({
          title: "Credits nicht ausreichend",
          description: `${message} Benötigt: ${creditsRequired}, Verfügbar: ${creditsAvailable}`,
          variant: "destructive",
          duration: 8000,
        });
        
        // Setze den Status für den Kauf-Button
        setInsufficientCredits({
          area: 'questions',
          creditsRequired,
          creditsAvailable
        });
        
        return;
      }
      
      toast({
        title: "Fehler",
        description: error.message || "Beim Generieren neuer Testfragen ist ein Fehler aufgetreten.",
        variant: "destructive",
      });
    }
  });

  // Mutation to reset session and load new topics
  const loadTopicsMutation = useMutation({
    mutationFn: async (existingSessionId?: string) => {
      // Wenn eine Session-ID übergeben wurde, lade nur die Daten für diese Session
      if (existingSessionId) {
        console.log('DEBUG: Loading data for existing session:', existingSessionId);
        
        try {
          // Token für die Authentifizierung abrufen
          const token = localStorage.getItem('exammaster_token');
          if (!token) {
            throw new Error('Nicht eingeloggt. Bitte melde dich an, um diese Funktion zu nutzen.');
          }
          
          // Klareres Logging
          console.log(`Sende Anfrage an: ${API_URL}/api/v1/results/${existingSessionId}`);
          
          // Verzögerung hinzufügen, um sicherzustellen, dass die Daten im Backend vollständig verfügbar sind
          await new Promise(resolve => setTimeout(resolve, 2000));
          
          // Zuerst überprüfen wir den Status der Session
          const checkStatusTimestamp = new Date().getTime();
          
          // Prüfe den Upload-Status mit session-info Endpoint
          const statusResponse = await axios.get<{ success: boolean; data: { processing_status: string } }>(
            `${API_URL}/api/v1/session-info/${existingSessionId}?nocache=${checkStatusTimestamp}`,
            { 
              withCredentials: true,
              headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Authorization': `Bearer ${token}`
              }
            }
          );
          
          // Überprüfe, ob der Upload-Status "completed" ist
          if (statusResponse.data.success && 
              statusResponse.data.data.processing_status !== "completed") {
            console.log(`Upload-Status ist noch nicht 'completed': ${statusResponse.data.data.processing_status}`);
            
            // Werfe eine spezifischere Fehlermeldung, die im Frontend besser behandelt werden kann
            throw new Error(`Die Session wird noch verarbeitet. Status: ${statusResponse.data.data.processing_status}`);
          }
          
          console.log("Upload-Status ist 'completed', lade Daten..");
        
          // Cache-busting Parameter hinzufügen, um aktuelle Daten zu erhalten
          const timestamp = new Date().getTime();
          const response = await axios.get<{ success: boolean; data: SessionData }>(
            `${API_URL}/api/v1/results/${existingSessionId}?nocache=${timestamp}`,
            { 
              withCredentials: true,
              headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Authorization': `Bearer ${token}`
              }
            }
          );
          
          // Debug-Log der Antwort
          console.log("API-Antwort erhalten:", response.status, response.statusText);
          
          // Vollständigen Inhalt der API-Antwort loggen
          console.log("VOLLSTÄNDIGE API-ANTWORT:", response.data);
          
          // Wenn Daten in der API-Antwort vorhanden sind, inspiziere sie genauer
          console.log("API-Antwort hat success:", response.data.success);
          // Sicherer Zugriff auf den Status, da er in beiden Formaten vorkommen kann
          console.log("API-Antwort hat status:", (response.data as any).status);
          console.log("API-Antwort data vorhanden:", !!response.data.data);
          console.log("API-Antwort Typ von data:", typeof response.data.data);
          
          // Anpassung an tatsächliches API-Antwortformat
          // Prüfe, ob es das erwartete Format oder das tatsächliche Format ist
          const hasExpectedFormat = response.data.success === true && 
                                   response.data.data && 
                                   (Array.isArray(response.data.data.flashcards) || 
                                    Array.isArray(response.data.data.test_questions));
          
          // Verwende any für das tatsächliche API-Antwortformat, da es ein anderes Schema hat
          const responseData = response.data as any;
          
          const hasActualFormat = responseData.status === "completed" && 
                                 responseData.data && 
                                 responseData.data.main_topic && 
                                 Array.isArray(responseData.data.topics);
          
          console.log("Hat erwartetes Format:", hasExpectedFormat);
          console.log("Hat tatsächliches Format:", hasActualFormat);
          
          if (hasExpectedFormat) {
            // Wenn es das erwartete Format hat, verwende es direkt
            localStorage.setItem('current_session_id', existingSessionId);
            return response.data.data;
          } else if (hasActualFormat) {
            // Wenn es das tatsächliche Format hat, adaptiere es
            console.log("Adaptiere API-Antwort zum erwarteten Format");
            
            // Erstelle eine Struktur, die dem erwarteten Format entspricht
            const adaptedData: SessionData = {
              session_id: existingSessionId,
              flashcards: new Array(responseData.data.flashcards_count || 0).fill({
                id: "placeholder",
                question: "Lade Flashcards...",
                answer: "Bitte warten..."
              }),
              test_questions: new Array(responseData.data.questions_count || 0).fill({
                id: "placeholder",
                text: "Lade Fragen...",
                options: ["Option 1", "Option 2", "Option 3", "Option 4"],
                correct_answer: 0
              }),
              analysis: {
                main_topic: responseData.data.main_topic || "Unbekanntes Thema",
                subtopics: Array.isArray(responseData.data.topics) ? 
                  responseData.data.topics.filter((t: string, i: number) => i > 0) : [],
                content_type: responseData.data.document_type,
                language: responseData.data.language,
                processing_status: responseData.status
              },
              topics: {
                main_topic: {
                  id: "main_topic_id",
                  name: responseData.data.main_topic
                },
                subtopics: Array.isArray(responseData.data.topics) ? 
                  responseData.data.topics.filter((t: string, i: number) => i > 0).map((name: string, i: number) => ({
                    id: `subtopic_${i}`,
                    name
                  })) : []
              },
              concept_map: {
                nodes: [
                  {
                    id: "main_topic_id",
                    text: responseData.data.main_topic,
                    isMainTopic: true
                  },
                  ...Array.isArray(responseData.data.topics) ? 
                    responseData.data.topics.filter((t: string, i: number) => i > 0).map((name: string, i: number) => ({
                      id: `subtopic_${i}`,
                      text: name
                    })) : []
                ],
                edges: []
              }
            };
            
            localStorage.setItem('current_session_id', existingSessionId);
            console.log("Adaptierte Daten:", adaptedData);
            return adaptedData;
          }
        } catch (error) {
          console.error("Fehler beim Laden der Themen (Details):", error);
          
          // Wenn der Status-Check fehlschlägt, werfen wir den Fehler weiter
          if (error.message && error.message.includes("Session wird noch verarbeitet")) {
            throw error; // Wir werfen den speziellen Status-Fehler
          }
          
          // Für andere Fehler werfen wir einen beschreibenden Fehler
          throw new Error(`Fehler beim Laden der Themen: ${error.message || 'Unbekannter Fehler'}`);
        }
      }
      
      // Wenn keine Session-ID übergeben wurde, starte eine völlig neue Session
      // Wir generieren eine temporäre ID für einen Redirect
      const redirectId = uuidv4();
      
      // Setze einen temporären State im sessionStorage, um zu signalisieren, dass wir alles neu laden wollen
      sessionStorage.setItem('force_new_session', 'true');
      sessionStorage.setItem('redirect_time', Date.now().toString());
      
      // Navigiere zu einer sicheren Zwischen-URL ohne Sessions und erzwinge einen harten Refresh
      window.location.href = `${window.location.pathname}?reset=${redirectId}`;
      
      return null; // Diese Zeile sollte nie erreicht werden, da wir vorher umleiten
    },
    onSuccess: (data) => {
      // Wenn Daten zurückgegeben wurden (bei bestehender Session), aktualisiere den State
      if (data && (data as any).flashcards) {
        const sessionData = data as SessionData;
        console.log('DEBUG: Successfully loaded session data:', sessionData);
        
        // Aktualisiere den State mit den neuen Daten
        setFlashcards(sessionData.flashcards || []);
        setQuestions(sessionData.test_questions || []);
        
        // Zeige keine Toast-Meldung, um den Benutzer nicht zu verwirren
      }
    },
    onError: (error: any) => {
      toast({
        title: "Fehler",
        description: error.message || "Beim Laden der Daten ist ein Fehler aufgetreten.",
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
        <div className="animate-pulse text-lg">{t('common.loading')}</div>
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
                  
                  // Entferne die Session-ID aus der URL, falls vorhanden
                  const url = new URL(window.location.href);
                  if (url.searchParams.has('session')) {
                    url.searchParams.delete('session');
                    window.history.replaceState({}, '', url.toString());
                  }
                  
                  // Zeige eine Benachrichtigung
                  toast({
                    title: t('index.newSession.title'),
                    description: t('index.newSession.description'),
                  });
                }}
              />
            </section>
            <section id="flashcards" className="section-container">
              <div className="max-w-5xl mx-auto">
                <div className="text-center mb-12 space-y-4">
                </div>
                
                {/* Credits-Fehlerbox anzeigen, wenn nicht genügend Credits vorhanden sind */}
                {insufficientCredits && insufficientCredits.area === 'flashcards' && (
                  <div className="mb-6 p-4 bg-destructive/10 border border-destructive/30 rounded-md flex flex-col md:flex-row justify-between items-center gap-4">
                    <div className="flex items-start gap-3">
                      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-destructive flex-shrink-0 mt-0.5">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      <div>
                        <h3 className="font-medium">{t('index.insufficientCredits.title')}</h3>
                        <p className="text-sm text-muted-foreground">
                          {t('index.insufficientCredits.flashcardsNeeded', { 
                            required: insufficientCredits.creditsRequired,
                            available: insufficientCredits.creditsAvailable 
                          })}
                        </p>
                      </div>
                    </div>
                    <Button 
                      onClick={() => {
                        window.location.href = "/payment";
                      }}
                      className="whitespace-nowrap"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mr-2">
                        <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
                        <line x1="1" y1="10" x2="23" y2="10" />
                      </svg>
                      {t('index.buyCredits')}
                    </Button>
                  </div>
                )}
                
                <FlashcardGenerator
                  flashcards={flashcards}
                  onGenerateMore={() => generateMoreFlashcardsMutation.mutate()}
                  isGenerating={generateMoreFlashcardsMutation.isPending}
                  tokenInfo={tokenInfoFlashcards}
                />
              </div>
            </section>
            <section id="test-simulator" className="section-container bg-secondary/30">
              <div className="max-w-5xl mx-auto">
                <div className="text-center mb-12 space-y-4">
                </div>
                
                {/* Credits-Fehlerbox anzeigen, wenn nicht genügend Credits vorhanden sind */}
                {insufficientCredits && insufficientCredits.area === 'questions' && (
                  <div className="mb-6 p-4 bg-destructive/10 border border-destructive/30 rounded-md flex flex-col md:flex-row justify-between items-center gap-4">
                    <div className="flex items-start gap-3">
                      <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-destructive flex-shrink-0 mt-0.5">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      <div>
                        <h3 className="font-medium">{t('index.insufficientCredits.title')}</h3>
                        <p className="text-sm text-muted-foreground">
                          {t('index.insufficientCredits.questionsNeeded', { 
                            required: insufficientCredits.creditsRequired,
                            available: insufficientCredits.creditsAvailable 
                          })}
                        </p>
                      </div>
                    </div>
                    <Button 
                      onClick={() => {
                        window.location.href = "/payment";
                      }}
                      className="whitespace-nowrap"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mr-2">
                        <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
                        <line x1="1" y1="10" x2="23" y2="10" />
                      </svg>
                      {t('index.buyCredits')}
                    </Button>
                  </div>
                )}
                
                <TestSimulator 
                  questions={questions}
                  onGenerateMore={() => generateMoreQuestionsMutation.mutate()}
                  isGenerating={generateMoreQuestionsMutation.isPending}
                  tokenInfo={tokenInfoQuestions}
                />
              </div>
            </section>
            <section id="concept-mapper">
              {sessionId && sessionId.length > 0 ? (
                <ConceptMapper 
                  sessionId={sessionId} 
                  conceptMapData={conceptMapData}
                />
              ) : (
                <div className="max-w-5xl mx-auto py-20 px-4 text-center">
                  <h2 className="text-3xl md:text-4xl font-bold mb-6">{t('conceptMap.title')}</h2>
                  <p className="text-lg text-muted-foreground mb-8">
                    {t('index.conceptMap.uploadPrompt')}
                  </p>
                </div>
              )}
            </section>
          </main>
          
          <Footer />
        </div>
      )}
    </>
  );
};

export default Index;

