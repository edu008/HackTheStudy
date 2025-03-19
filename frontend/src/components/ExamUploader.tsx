import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FileText, Upload, CheckCircle, Loader2, X, AlertCircle, BookOpen } from 'lucide-react';
import { useToast } from "@/hooks/use-toast";
import { useMutation } from '@tanstack/react-query';
import axios from 'axios';
import { Progress } from "@/components/ui/progress";

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// Maximum context size in tokens
const MAX_CONTEXT_SIZE = 128000; // GPT-4o Kontextgröße
// Reserviert für Systemprompt und Antwort
const RESERVED_TOKENS = 8000;
// Effektiv nutzbare Tokens für den Eingabetext
const USABLE_TOKENS = MAX_CONTEXT_SIZE - RESERVED_TOKENS;
// Verhältnis zwischen Zeichen und Tokens (1 Token ≈ 4 Zeichen)
const CHARS_PER_TOKEN = 4;

// This interface matches the response from the backend's upload endpoint
interface BackendUploadResponse {
  success: boolean;
  message: string;
  session_id: string;
  task_id: string;
  file_position?: number;
  files_count?: number;
  new_file_tokens?: number;
  current_processing_status?: string;
  task_started?: boolean;
}

// This interface matches the response from the backend's results endpoint
interface SessionData {
  flashcards: {
    id: string;
    question: string;
    answer: string;
  }[];
  test_questions: {
    id: string;
    text: string;
    options: string[];
    correctAnswer: number;
    explanation?: string;  // Make explanation optional to support both old and new questions
  }[];
  analysis: {
    main_topic: string;
    subtopics: string[];
    content_type?: string;
    language?: string;
    processing_status?: string; // Status-Information vom Backend
    files?: string[];
  };
}

// This interface matches what the parent component expects
interface UploadResponse {
  success: boolean;
  message: string;
  flashcards: {
    id: string;
    question: string;
    answer: string;
  }[];
  questions: {
    id: string;
    text: string;
    options: string[];
    correctAnswer: number;
    explanation?: string;
  }[];
  session_id: string;
}

// Eine Funktion zur Schätzung der Token-Anzahl basierend auf der Dateigröße
const estimateTokensFromFile = async (file: File): Promise<number> => {
  // Kalibrierungsfaktor (empirisch ermittelt) - reduziert die Schätzung, da wir überschätzen
  const CALIBRATION_FACTOR = 0.2; // Reduziert auf 20% für GPT-4o, da wir einen größeren Kontext haben
  
  // Für PDF-Dateien
  if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
    // PDFs enthalten oft mehr Zeichen als Tokens nach der Extraktion
    // Konservativere Schätzung: ~100 Tokens pro KB für PDFs (mit Kalibrierung)
    return Math.round((file.size / 1024) * 100 * CALIBRATION_FACTOR);
  }
  
  // Für Textdateien
  if (file.type === 'text/plain' || file.name.toLowerCase().endsWith('.txt')) {
    // Schätzung: 1 KB ~= 1000 Zeichen ~= 250 Tokens (4 Zeichen pro Token)
    // Mit Kalibrierung angepasst
    return Math.round((file.size / 1024) * 250 * CALIBRATION_FACTOR);
  }
  
  // Fallback für andere Dateitypen
  return Math.round((file.size / 1024) * 150 * CALIBRATION_FACTOR);
};

// Eine Funktion zur Berechnung der gesamten Token-Anzahl für mehrere Dateien
const estimateTotalTokens = async (files: File[]): Promise<number> => {
  if (files.length === 0) return 0;
  
  const tokenPromises = files.map(file => estimateTokensFromFile(file));
  const tokenCounts = await Promise.all(tokenPromises);
  
  return tokenCounts.reduce((total, count) => total + count, 0);
};

// Funktion zum Prüfen, ob eine PDF wahrscheinlich problematische Binärdaten enthält
const containsBinaryContent = async (file: File): Promise<boolean> => {
  // Wir akzeptieren alle PDFs, da wir die Server-seitige Bereinigung verbessert haben
  return false;
};

// Eine Funktion zur Validierung von Dateien vor dem Upload
const validateFilesBeforeUpload = async (filesToCheck: File[]): Promise<{ valid: boolean; errorMessage?: string }> => {
  // Akzeptiere alle Dateien, da wir die Server-seitige Verarbeitung verbessert haben
  return { valid: true };
};

interface ExamUploaderProps {
  onUploadSuccess?: (data: UploadResponse) => void;
  sessionId?: string;
  loadTopicsMutation?: any; // Using any to avoid type conflicts
  onResetSession?: () => void; // Neue Prop für das Zurücksetzen der Session
}

const ExamUploader = ({ onUploadSuccess, sessionId, loadTopicsMutation, onResetSession }: ExamUploaderProps) => {
  const { toast } = useToast();
  const [files, setFiles] = useState<File[]>([]);
  const [isUploaded, setIsUploaded] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [tokenEstimate, setTokenEstimate] = useState<number>(0);
  const [contextPercentage, setContextPercentage] = useState<number>(0);
  const [isEstimating, setIsEstimating] = useState<boolean>(false);
  const [existingSessionTokens, setExistingSessionTokens] = useState<number>(0);
  const [isLoadingSessionInfo, setIsLoadingSessionInfo] = useState<boolean>(false);
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(0);
  const [sessionFiles, setSessionFiles] = useState<string[]>([]);
  const [isProcessingNotified, setIsProcessingNotified] = useState<boolean>(false);

  // Funktion zum Abrufen von Informationen über eine bestehende Session
  const fetchExistingSessionTokens = async (sessionId: string | undefined) => {
    if (!sessionId) {
      setExistingSessionTokens(0);
      setSessionFiles([]);
      return 0;
    }
    
    setIsLoadingSessionInfo(true);
    try {
      const token = localStorage.getItem('exammaster_token');
      
      // API-Endpunkt für Session-Informationen abrufen
      const response = await axios.get<{success: boolean, data: {token_count: number, processing_status: string, files: string[]}}>(
        `${API_URL}/api/v1/session-info/${sessionId}`,
        {
          headers: {
            'Authorization': token ? `Bearer ${token}` : '',
          },
          withCredentials: true,
          timeout: 10000 // 10 Sekunden Timeout
        }
      );
      
      if (response.data.success && response.data.data) {
        const sessionData = response.data.data;
        const tokenCount = sessionData.token_count || 0;
        const existingFilesCount = sessionData.files.length || 0;
        const now = Date.now();
        
        // Speichere die Dateiliste
        setSessionFiles(sessionData.files || []);
        
        console.log(`DEBUG: Session ${sessionId} - Token count: ${tokenCount}, Status: ${sessionData.processing_status}, Files: ${existingFilesCount}`);
        
        // Aktualisiere den existingSessionTokens-Wert
        setExistingSessionTokens(tokenCount);
        
        // Speichere den Zeitpunkt der letzten Aktualisierung trotzdem für andere Zwecke
        setLastUpdateTime(now);
        
        // Zeige eine Warnung nur noch einmal, wenn bereits die maximale Anzahl an Dateien erreicht ist und Dateien ausgewählt sind
        if (existingFilesCount >= 5 && files.length > 0) {
          toast({
            title: "Maximale Anzahl an Dateien erreicht",
            description: "Diese Session enthält bereits 5 Dateien. Bitte erstelle eine neue Session, wenn du weitere Dateien hochladen möchtest.",
            variant: "destructive",
          });
          // Leere die ausgewählten Dateien
          setFiles([]);
        }
        
        // Zeige einen Verarbeitungshinweis nur beim ersten Erkennen des Status "processing"
        if (sessionData.processing_status === "processing" && !isProcessingNotified) {
          setIsProcessingNotified(true);
          toast({
            title: "Session wird verarbeitet",
            description: `Die Session mit ${existingFilesCount} Dateien wird gerade analysiert. Bitte warte einen Moment.`,
            variant: "default",
          });
        } else if (sessionData.processing_status !== "processing") {
          setIsProcessingNotified(false);
        }
        
        return tokenCount;
      }
      
      // Wenn die Antwort keinen Erfolg zeigt oder keine Daten enthält, trotzdem eine leere Session verwenden
      console.warn("Session-Info-Antwort enthielt keine gültigen Daten:", response.data);
      return 0;
    } catch (error) {
      console.error('Fehler beim Abrufen der Session-Informationen:', error);
      throw error; // Fehler weitergeben, damit der Aufrufer erneut versuchen kann
    } finally {
      setIsLoadingSessionInfo(false);
    }
  };

  // Aktualisiere die Session-Informationen in regelmäßigen Abständen
  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null;
    let retryCount = 0;
    
    // Beim ersten Laden und bei Änderungen der sessionId
    const loadSessionInfo = async () => {
      if (sessionId) {
        // Initial die Session-Informationen laden
        try {
          await fetchExistingSessionTokens(sessionId);
          retryCount = 0; // Zurücksetzen bei Erfolg
        } catch (error) {
          console.error("Fehler beim Laden der Session-Informationen:", error);
          // Bei Fehlern bis zu 3 Mal wiederholen
          if (retryCount < 3) {
            retryCount++;
            setTimeout(loadSessionInfo, 2000); // Erneut versuchen nach 2 Sekunden
          }
        }
        
        // Alle 10 Sekunden die Session-Informationen aktualisieren
        intervalId = setInterval(async () => {
          try {
            await fetchExistingSessionTokens(sessionId);
          } catch (error) {
            console.error("Fehler beim periodischen Aktualisieren der Session:", error);
          }
        }, 10000);
      } else {
        // Setze existingSessionTokens und sessionFiles auf 0/leer, wenn keine sessionId vorhanden ist
        setExistingSessionTokens(0);
        setSessionFiles([]);
      }
    };
    
    // Starte das Laden
    loadSessionInfo();
    
    // Cleanup beim Unmount oder wenn sessionId sich ändert
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [sessionId]);

  // Aktualisiere die Token-Schätzung, wenn sich die Dateien ändern
  useEffect(() => {
    const updateTokenEstimate = async () => {
      if (files.length === 0 && existingSessionTokens === 0) {
        setTokenEstimate(0);
        setContextPercentage(0);
        return;
      }
      
      setIsEstimating(true);
      const newFilesTokens = await estimateTotalTokens(files);
      const totalTokens = newFilesTokens + existingSessionTokens;
      
      setTokenEstimate(totalTokens);
      setContextPercentage(Math.min(100, (totalTokens / USABLE_TOKENS) * 100));
      setIsEstimating(false);
      
      console.log(`DEBUG: Estimated tokens - Existing: ${existingSessionTokens}, New files: ${newFilesTokens}, Total: ${totalTokens}`);
    };
    
    updateTokenEstimate();
  }, [files, existingSessionTokens]);

  const uploadMutation = useMutation({
    mutationFn: async (filesToUpload: File[]) => {
      // Erstelle eine neue Array-Kopie, um die originalen files nicht zu manipulieren
      const filesToProcess = [...filesToUpload];
      
      // Aktualisiere den Upload-Fortschritt auf 0, wenn wir anfangen
      setUploadProgress(0);
      setError(null);
      
      let currentSessionId = sessionId;
      
      // Ergebnisse aller Uploads speichern
      const uploadResults = [];
      let totalNewTokens = 0; // Variable für die Summe der neuen Tokens
      
      // Verarbeite alle Dateien nacheinander
      for (let i = 0; i < filesToProcess.length; i++) {
        const file = filesToProcess[i];
        setUploadProgress((i / filesToUpload.length) * 50); // Die ersten 50% für Upload
        
        // FormData für diese Datei
        const formData = new FormData();
        formData.append('file', file);
        
        // Füge die Session-ID hinzu, falls vorhanden (für alle Dateien nach der ersten)
        if (currentSessionId) {
          formData.append('session_id', currentSessionId);
        }
        
        // Token hinzufügen, falls verfügbar
        const token = localStorage.getItem('exammaster_token');
        
        // Option zum Extrahieren von nur Text hinzufügen (für PDFs mit Bildern)
        formData.append('extract_text_only', 'true');
        formData.append('clean_pdf', 'true');
        // Neue Optionen für verbessertes PDF-Parsing
        formData.append('remove_null_bytes', 'true');
        formData.append('strip_binary', 'true');
        formData.append('force_plain_text', 'true');
        // Option hinzufügen, um Daten erst nach erfolgreicher Prüfung zu speichern
        formData.append('validate_before_save', 'true');
        // Neue Option: Aggressives Bereinigen von problematischen Zeichen
        formData.append('aggressive_cleaning', 'true');
        
        try {
          console.log(`DEBUG: Uploading file: ${file.name}`);
          setUploadProgress((i / filesToUpload.length) * 50); // Die ersten 50% für Upload
          
          const response = await axios.post<BackendUploadResponse>(
            `${API_URL}/api/v1/upload`, 
            formData, 
            {
              headers: {
                'Content-Type': 'multipart/form-data',
                'Authorization': token ? `Bearer ${token}` : '',
              },
              withCredentials: true,
            }
          );
          
          console.log(`DEBUG: Upload response for file ${i+1}:`, response.data);
          
          // Prüfen, ob die Antwort Fehler enthält
          if (!response.data.success) {
            throw new Error(`Fehler beim Verarbeiten von Datei ${file.name}: ${response.data.message || 'Unbekannter Fehler'}`);
          }
          
          // Aktualisiere die Token-Anzahl für die Session
          if (response.data.new_file_tokens) {
            totalNewTokens += response.data.new_file_tokens;
            setExistingSessionTokens(prev => prev + response.data.new_file_tokens);
          }
          
          // Wenn dies die erste Datei ist, speichere die Session-ID für nachfolgende Uploads
          if (!currentSessionId && response.data.session_id) {
            currentSessionId = response.data.session_id;
          }
          
          // Speichere das Ergebnis für spätere Verarbeitung
          uploadResults.push(response.data);
        } catch (error: any) {
          console.error(`DEBUG: Error uploading file ${i+1}:`, error);
          
          // Spezifische Fehlermeldung für korrupte PDF-Dateien
          if (error.response?.data?.error?.code === 'CORRUPTED_PDF' || 
              (error.message && error.message.toLowerCase().includes('korrupt')) ||
              (error.message && error.message.toLowerCase().includes('beschädigt'))) {
            
            // Zeige einen Toast mit detaillierten Informationen
            toast({
              title: "Korrupte PDF erkannt",
              description: `Die Datei "${file.name}" scheint beschädigt zu sein oder enthält komplexe Strukturen, die nicht verarbeitet werden können. Diese Datei wird übersprungen.`,
              variant: "destructive",
              duration: 10000, // Längere Anzeigedauer (10 Sekunden)
            });
            
            // Entferne die korrupte Datei aus der Dateiliste
            setFiles(prevFiles => prevFiles.filter(f => f.name !== file.name));
            
            // Fahre mit den anderen Dateien fort, wenn vorhanden
            continue;
          }
          
          // Spezifische Fehlermeldung für Binärdaten/Null-Bytes
          if (error.message?.includes('NUL (0x00)') || 
              error.response?.data?.message?.includes('NUL') ||
              error.response?.data?.message?.includes('cannot contain NUL') ||
              error.message?.includes('cannot contain NUL')) {
            throw new Error(`Die Datei '${file.name}' enthält Binärdaten oder Null-Bytes, die nicht verarbeitet werden können. Bitte konvertiere die PDF in ein Textformat oder verwende einen PDF-Editor, um die Datei zu bereinigen.`);
          }
          
          // Spezifische Fehlermeldung für annotierte PDFs
          if (error.message?.includes('annotierte') ||
              error.message?.includes('annotation') ||
              error.message?.toLowerCase().includes('annot') ||
              file.name.toLowerCase().includes('annot')) {
            throw new Error(`Die Datei '${file.name}' enthält komplexe Anmerkungen, die Probleme verursachen können. Diese PDF-Datei konnte nicht vollständig verarbeitet werden.`);
          }
          
          // Werfe den ursprünglichen Fehler weiter, wenn keine spezifische Behandlung nötig ist
          throw error;
        }
      }
      
      // Nach dem Upload aller Dateien auf die Verarbeitung warten
      console.log('DEBUG: All files uploaded, waiting for processing...');
      console.log(`DEBUG: Total new tokens added: ${totalNewTokens}`);
      
      // Kurze Pause, um dem Backend Zeit zu geben, die Verarbeitung zu starten
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Poll the results endpoint until the data is available
      let retries = 0;
      const maxRetries = 90; // Erhöht auf 90 (ca. 3 Minuten Wartezeit)
      const retryInterval = 2000; // 2 Sekunden
      
      // Tracking für den letzten bekannten Status
      let lastStatus = "";
      let lastFlashcardCount = 0;
      let lastQuestionCount = 0;
      let statusChangeTime = Date.now();
      
      // Wenn es sich um eine annotierte PDF handelt, zeige einen Hinweis auf längere Verarbeitungszeit
      const hasAnnotatedPDF = filesToUpload.some(file => 
        file.name.toLowerCase().includes('annot') || 
        file.name.toLowerCase().includes('comment') ||
        file.name.toLowerCase().includes('markup'));
        
      if (hasAnnotatedPDF) {
        toast({
          title: "Hinweis zur Verarbeitung",
          description: "Annotierte PDFs benötigen mehr Zeit zur Verarbeitung. Bitte haben Sie etwas Geduld.",
          duration: 8000,
        });
      }

      // Hol den Token für die API-Anfragen
      const token = localStorage.getItem('exammaster_token');

      while (retries < maxRetries) {
        try {
          setUploadProgress(50 + ((retries / maxRetries) * 50)); // Die anderen 50% für Verarbeitung
          
          // Cache-busting Parameter hinzufügen um aktuelle Daten zu erhalten
          const timestamp = new Date().getTime();
          const resultsResponse = await axios.get<{ success: boolean, data: SessionData }>(
            `${API_URL}/api/v1/results/${currentSessionId}?nocache=${timestamp}`,
            { 
              headers: {
                'Authorization': token ? `Bearer ${token}` : '',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
              },
              withCredentials: true 
            }
          );
          
          if (resultsResponse.data.success && resultsResponse.data.data) {
            // Daten analysieren, um zu sehen, ob die Verarbeitung abgeschlossen ist
            const flashcards = resultsResponse.data.data.flashcards || [];
            const questions = resultsResponse.data.data.test_questions || [];
            const processingStatus = resultsResponse.data.data.analysis?.processing_status || "";
            
            console.log(`DEBUG: Poll ${retries}/${maxRetries} - Status: ${processingStatus}, Flashcards: ${flashcards.length}, Questions: ${questions.length}`);
            
            // Status-Änderung erkennen
            if (processingStatus !== lastStatus || 
                flashcards.length !== lastFlashcardCount || 
                questions.length !== lastQuestionCount) {
              lastStatus = processingStatus;
              lastFlashcardCount = flashcards.length;
              lastQuestionCount = questions.length;
              statusChangeTime = Date.now();
              console.log(`DEBUG: Status/Daten haben sich geändert, setze Timer zurück`);
            }
            
            // Wenn Status "completed" ist und wir Daten haben, UND
            // seit der letzten Status-Änderung mind. 5 Sekunden vergangen sind
            const timeInCurrentStatus = Date.now() - statusChangeTime;
            const hasStabilized = timeInCurrentStatus >= 5000; // 5 Sekunden Stabilitätsprüfung
            
            // Bei annotierten PDFs längere Stabilisierungszeit (8 Sekunden)
            const stabilizationTime = hasAnnotatedPDF ? 8000 : 5000;
            const annotatedHasStabilized = timeInCurrentStatus >= stabilizationTime;
            
            const finalStabilized = hasAnnotatedPDF ? annotatedHasStabilized : hasStabilized;
            
            if (processingStatus === "completed" && 
                flashcards.length > 0 && 
                questions.length > 0 && 
                finalStabilized) {
              console.log(`DEBUG: Verarbeitung abgeschlossen, status stabil seit ${timeInCurrentStatus}ms, kehre zurück`);
              
              // Combine the upload response and results data
              const completeResponse: UploadResponse = {
                success: true,
                message: "Dateien erfolgreich hochgeladen und verarbeitet.",
                session_id: currentSessionId,
                flashcards: flashcards,
                questions: questions
              };
              
              return completeResponse;
            } 
            
            // Wenn prozessing und erste Antwort mit completed, ignorieren und weiter warten
            if (processingStatus === "completed" && retries < 10 && 
                flashcards.length > 0 && questions.length > 0) {
              console.log("DEBUG: Status 'completed', aber warte auf Stabilität...");
            }
            // Bei Status "processing" oder bis retries >= 30 warten wir weiter
            else if (processingStatus === "processing" || retries < 30) {
              console.log("DEBUG: Backend verarbeitet noch die Daten, warte weiter...");
            }
            
            // Wenn wir abwarten, aber zu lange keine Änderung, und genug Daten haben
            if (retries >= 30 && flashcards.length > 0 && questions.length > 0 && timeInCurrentStatus >= 20000) {
              console.log("DEBUG: Keine Änderung nach 20 Sekunden, breche mit aktuellen Daten ab");
              
              // Verwende die aktuellen Daten
              const completeResponse: UploadResponse = {
                success: true,
                message: "Dateien erfolgreich hochgeladen und verarbeitet.",
                session_id: currentSessionId,
                flashcards: flashcards,
                questions: questions
              };
              
              return completeResponse;
            }
          }
        } catch (error) {
          console.error(`DEBUG: Error checking results (attempt ${retries+1}):`, error);
        }
        
        // Wait before retrying
        await new Promise(resolve => setTimeout(resolve, retryInterval));
        retries++;
      }
      
      // If we've exhausted all retries, return a partial response with an error message
      return {
        success: true,
        message: "Dateien hochgeladen, aber die Verarbeitung dauert länger als erwartet. Der Server könnte überlastet sein. Versuche später, die Ergebnisse in deiner Historie anzuzeigen.",
        session_id: currentSessionId,
        flashcards: [],
        questions: []
      };
    },
    onSuccess: (data) => {
      setIsUploaded(true);
      
      if (data.flashcards.length === 0 && data.questions.length === 0) {
        // Show a warning toast if no flashcards or questions were generated
        toast({
          title: "Dateien hochgeladen",
          description: data.message || "Die Dateien wurden hochgeladen, aber es konnten keine Lernmaterialien erstellt werden. Bitte versuche es später erneut.",
          variant: "default",
        });
      } else {
        // Show a success toast if flashcards or questions were generated
        toast({
          title: "Dateien hochgeladen",
          description: `${files.length} Prüfung${files.length > 1 ? 'en wurden' : ' wurde'} erfolgreich hochgeladen und analysiert.`,
        });
      }
      
      if (onUploadSuccess) {
        console.log('DEBUG: Calling onUploadSuccess with data');
        onUploadSuccess(data);
      }
    },
    onError: (error: any) => {
      console.error('DEBUG: Upload error:', error);
      console.error('DEBUG: Error response:', error.response?.data);
      setError(error.message);
      toast({
        title: "Fehler beim Hochladen",
        description: `Es gab ein Problem: ${error.message}`,
        variant: "destructive",
      });
    },
  });

  // Funktion zum Prüfen, ob eine PDF wahrscheinlich problematische Binärdaten enthält
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    
    // Reset des Input-Felds für bessere Benutzererfahrung
    e.target.value = '';
    
    if (selectedFiles.length > 0) {
      // Prüfe, ob die maximale Anzahl an Dateien in der Session bereits erreicht ist
      if (sessionFiles.length >= 5) {
        toast({
          title: "Maximale Anzahl an Dateien erreicht",
          description: "Diese Session enthält bereits 5 Dateien. Bitte erstelle eine neue Session für weitere Dateien.",
          variant: "destructive",
        });
        return;
      }
      
      // Prüfe, ob die maximale Anzahl an gleichzeitig hochladbaren Dateien überschritten wird
      if (files.length + selectedFiles.length > 5) {
        toast({
          title: "Zu viele Dateien",
          description: "Du kannst maximal 5 Dateien gleichzeitig hochladen.",
          variant: "destructive",
        });
        return;
      }
      
      const invalidFiles = selectedFiles.filter(file => {
        const fileType = file.type;
        const fileExtension = file.name.split('.').pop()?.toLowerCase();
        
        return !(fileType === 'application/pdf' || 
                fileType === 'text/plain' || 
                fileExtension === 'pdf' || 
                fileExtension === 'txt');
      });
      
      if (invalidFiles.length > 0) {
        toast({
          title: "Ungültiges Format",
          description: "Bitte nur PDF- oder TXT-Dateien hochladen.",
          variant: "destructive",
        });
        return;
      }
      
      // Hinweis auf annotierte PDFs, die möglicherweise Probleme verursachen könnten
      const annotatedPDFs = selectedFiles.filter(file => 
        file.name.toLowerCase().includes('annot') || 
        file.name.toLowerCase().includes('comment') ||
        file.name.toLowerCase().includes('markup'));
      
      if (annotatedPDFs.length > 0) {
        toast({
          title: "Hinweis zu annotierten PDFs",
          description: "Es wurden PDF-Dateien mit möglichen Anmerkungen erkannt. Die Textextraktion kann bei solchen Dateien beeinträchtigt sein.",
          duration: 6000,
        });
      }
      
      // Prüfe auf problematische Binärdaten in PDFs
      validateFilesBeforeUpload(selectedFiles).then(result => {
        if (!result.valid) {
          toast({
            title: "Problematische Datei erkannt",
            description: result.errorMessage,
            variant: "destructive",
            duration: 8000,
          });
          return;
        }
        
        // Wenn alles in Ordnung ist, Dateien hinzufügen
        setFiles(prevFiles => [...prevFiles, ...selectedFiles]);
        
        // Bestätigungshinweis für die Auswahl
        toast({
          title: "Dateien ausgewählt",
          description: `${selectedFiles.length} Dateien wurden ausgewählt und können jetzt hochgeladen werden.`,
        });
      });
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    
    const droppedFiles = Array.from(e.dataTransfer.files);
    
    // Prüfe, ob die maximale Anzahl an Dateien in der Session bereits erreicht ist
    if (sessionFiles.length >= 5) {
      toast({
        title: "Maximale Anzahl an Dateien erreicht",
        description: "Diese Session enthält bereits 5 Dateien. Bitte erstelle eine neue Session für weitere Dateien.",
        variant: "destructive",
      });
      return;
    }
    
    // Prüfe, ob die maximale Anzahl an gleichzeitig hochladbaren Dateien überschritten wird
    if (files.length + droppedFiles.length > 5) {
      toast({
        title: "Zu viele Dateien",
        description: "Du kannst maximal 5 Dateien gleichzeitig hochladen.",
        variant: "destructive",
      });
      return;
    }
    
    const invalidFiles = droppedFiles.filter(file => {
      const fileType = file.type;
      const fileExtension = file.name.split('.').pop()?.toLowerCase();
      
      return !(fileType === 'application/pdf' || 
              fileType === 'text/plain' || 
              fileExtension === 'pdf' || 
              fileExtension === 'txt');
    });
    
    if (invalidFiles.length > 0) {
      toast({
        title: "Ungültiges Format",
        description: "Bitte nur PDF- oder TXT-Dateien hochladen.",
        variant: "destructive",
      });
      return;
    }
    
    // Prüfe auf problematische Binärdaten in PDFs
    validateFilesBeforeUpload(droppedFiles).then(result => {
      if (!result.valid) {
        toast({
          title: "Problematische Datei erkannt",
          description: result.errorMessage,
          variant: "destructive",
          duration: 8000,
        });
        return;
      }
      
      // Wenn alles in Ordnung ist, Dateien hinzufügen
      setFiles(prevFiles => [...prevFiles, ...droppedFiles]);
      
      // Bestätigungshinweis für die Auswahl
      toast({
        title: "Dateien hinzugefügt",
        description: `${droppedFiles.length} Dateien wurden hinzugefügt. Klicke auf "Hochladen", um fortzufahren.`,
        variant: "default",
      });
    });
  };

  const handleUpload = () => {
    if (files.length === 0) return;
    
    // Überprüfe auf Tokenlimit vor dem Upload
    const totalTokens = tokenEstimate; // Dies umfasst bereits bestehende + neue Tokens
    if (totalTokens > USABLE_TOKENS) {
      toast({
        title: "Dateien zu groß",
        description: `Die Gesamtgröße überschreitet das maximale Tokenlimit (${totalTokens.toLocaleString()} von max. ${USABLE_TOKENS.toLocaleString()}). Bitte verwenden Sie kleinere Dateien.`,
        variant: "destructive",
      });
      setError(`Die Dateien sind zu groß für die Verarbeitung. Maximale Kontextgröße: ${USABLE_TOKENS.toLocaleString()} Tokens, Geschätzte Gesamtgröße: ${totalTokens.toLocaleString()} Tokens.`);
      return;
    }
    
    // Finale Prüfung auf problematische Dateien vor dem Upload
    validateFilesBeforeUpload(files).then(result => {
      if (!result.valid) {
        toast({
          title: "Upload abgebrochen",
          description: result.errorMessage,
          variant: "destructive",
          duration: 8000,
        });
        setError(result.errorMessage);
        return;
      }
      
      console.log('DEBUG: handleUpload called with files:', files);
      setError(null);
      setUploadProgress(0);
      
      // Information anzeigen, wenn mehrere Dateien hochgeladen werden
      if (files.length > 1) {
        toast({
          title: "Mehrere Dateien werden hochgeladen",
          description: "Alle Dateien werden in einer gemeinsamen Analyse kombiniert und verarbeitet. Bei PDFs mit Bildern können Fehler auftreten. Lade Dateien einzeln hoch für bessere Ergebnisse.",
          variant: "default",
          duration: 6000,
        });
      }
      
      // Wenn bereits eine bestehende Session vorhanden ist, zeige einen Hinweis
      if (existingSessionTokens > 0) {
        toast({
          title: "Dateien werden zu bestehender Sitzung hinzugefügt",
          description: "Die neuen Dateien werden zur bestehenden Sitzung hinzugefügt und alle Daten werden neu analysiert.",
          variant: "default",
        });
      }
      
      uploadMutation.mutate(files);
    });
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const removeFile = (index: number) => {
    setFiles(prevFiles => prevFiles.filter((_, i) => i !== index));
  };

  const resetUpload = () => {
    setFiles([]);
    setIsUploaded(false);
    setError(null);
    setTokenEstimate(0);
    setContextPercentage(0);
  };
  
  // Berechne den verfügbaren Prozentsatz des Kontextes
  const contextAvailablePercentage = 100 - contextPercentage;
  
  // Zeigen Sie klarer an, wie viele Tokens bereits vorhanden sind und wie viele hinzukommen
  const getTokensDisplay = () => {
    if (isEstimating) {
      return 'Wird berechnet...';
    }
    
    const existingTokensText = existingSessionTokens > 0 
      ? `${existingSessionTokens.toLocaleString()} vorhandene`
      : '';
      
    const newTokensEstimate = files.length > 0
      ? (tokenEstimate - existingSessionTokens)
      : 0;
      
    const newTokensText = newTokensEstimate > 0
      ? `${newTokensEstimate.toLocaleString()} neue`
      : '';
      
    const totalText = `${tokenEstimate.toLocaleString()} / ${USABLE_TOKENS.toLocaleString()} Tokens`;
    
    if (existingTokensText && newTokensText) {
      return `${existingTokensText} + ${newTokensText} = ${totalText}`;
    } else if (existingTokensText) {
      return `${existingTokensText} = ${totalText}`;
    } else if (newTokensText) {
      return `${newTokensText} = ${totalText}`;
    } else {
      return totalText;
    }
  };

  return (
    <section id="upload" className="section-container">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12 space-y-4">
          <h2 className="text-3xl md:text-4xl font-bold animate-fade-in">
            Lade deine Prüfungen hoch
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto animate-fade-in">
            Stelle uns deine alten Moodle-Prüfungen zur Verfügung, und unsere KI (GPT-4o) wird daraus optimales Lernmaterial erstellen.
          </p>
        </div>
        
        <Card className="border border-border/50 shadow-soft overflow-hidden animate-slide-up relative">
          <CardHeader className="pb-4">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center">
              <div>
                <CardTitle className="flex items-center gap-2">
                  Prüfungen hochladen
                </CardTitle>
                <CardDescription>
                  Unterstützte Formate: PDF, TXT (max. 5 Dateien)
                </CardDescription>
                {sessionId && (
                  <div className="text-xs text-muted-foreground mt-1">
                    {isLoadingSessionInfo ? (
                      <span className="flex items-center">
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                        Lade Session-Informationen...
                      </span>
                    ) : existingSessionTokens > 0 ? (
                      <div className="space-y-1">
                        {sessionFiles.length >= 5 && (
                          <span className="flex items-center text-xs text-amber-500 font-medium ml-4">
                            <span className="inline-block w-3 h-3 rounded-full bg-amber-500/30 mr-1"></span>
                            Maximale Anzahl von 5 Dateien erreicht
                          </span>
                        )}
                        {files.length > 0 && sessionFiles.length < 5 && (
                          <span className="flex items-center text-xs text-muted-foreground ml-4">
                            <span className="inline-block w-3 h-3 rounded-full bg-primary/20 mr-1"></span>
                            + Neue Dateien: ~{(tokenEstimate - existingSessionTokens).toLocaleString()} geschätzte Tokens
                          </span>
                        )}
                      </div>
                    ) : (
                      <span>Session-ID: {sessionId}</span>
                    )}
                  </div>
                )}
              </div>
              
              {/* "Neue Themen laden" Button - nur anzeigen, wenn eine Session geladen ist */}
              {sessionId && loadTopicsMutation && (
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    
                    // Lösche die spezifische Session-ID im Backend
                    try {
                      const token = localStorage.getItem('exammaster_token');
                      fetch(`${API_URL}/api/v1/session/reset`, {
                        method: 'POST',
                        headers: {
                          'Content-Type': 'application/json',
                          'Authorization': token ? `Bearer ${token}` : ''
                        },
                        credentials: 'include',
                        body: JSON.stringify({ session_id: sessionId })
                      }).catch(err => console.error('Session reset error:', err));
                    } catch (error) {
                      console.error('Failed to reset session:', error);
                    }
                    
                    // Bewahre wichtige Authentifizierungsdaten
                    const authToken = localStorage.getItem('exammaster_token');
                    const userData = localStorage.getItem('exammaster_user');
                    
                    // Lösche nur session-bezogene Daten, nicht die Auth-Daten
                    localStorage.removeItem('current_session_id');
                    localStorage.removeItem('session_id');
                    localStorage.removeItem('last_session_id');
                    sessionStorage.clear();
                    
                    // Stelle Authentifizierungsdaten wieder her
                    if (authToken) localStorage.setItem('exammaster_token', authToken);
                    if (userData) localStorage.setItem('exammaster_user', userData);
                    
                    // Zur Startseite navigieren mit einem Random-Parameter, um jeglichen Cache zu vermeiden
                    window.location.href = '/?nocache=' + Math.random().toString(36).substring(2,15);
                  }}
                  className="flex items-center gap-2 mt-2 md:mt-0 relative z-10 px-4 py-2 text-sm font-medium border rounded-md"
                  id="load-topics-btn"
                >
                  <BookOpen className="h-4 w-4" />
                  Neue Session starten
                </a>
              )}
            </div>
          </CardHeader>
          
          <CardContent>
            {!isUploaded ? (
              <>
                <div 
                  className={`p-8 border-2 border-dashed rounded-lg flex flex-col items-center justify-center gap-4 transition-all relative ${
                    files.length > 0 ? 'border-primary/50 bg-primary/5' : 'border-border hover:border-primary/30 hover:bg-secondary/50'
                  }`}
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                >
                  {files.length > 0 ? (
                    <div className="w-full">
                      <div className="flex flex-col items-center gap-3 mb-6 animate-fade-in">
                        <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
                          <FileText className="h-8 w-8 text-primary" />
                        </div>
                        <div className="text-center">
                          <p className="font-medium">
                            {files.length === 1 ? "1 Datei ausgewählt" : `${files.length} Dateien ausgewählt`}
                          </p>
                          <span className="text-xs text-muted-foreground">
                            Gesamtgröße: {isEstimating ? "Wird berechnet..." : getTokensDisplay()}
                          </span>
                        </div>
                      </div>
                      
                      <div className="space-y-2 max-h-60 overflow-y-auto pr-2">
                        {files.map((file, index) => (
                          <div key={index} className="flex items-center justify-between p-3 bg-background rounded-md border border-border/70 hover:border-primary/30 transition-colors">
                            <div className="flex items-center gap-3 overflow-hidden">
                              <div className="h-10 w-10 flex-shrink-0 rounded-md bg-primary/10 flex items-center justify-center">
                                <FileText className="h-5 w-5 text-primary" />
                              </div>
                              <div className="overflow-hidden">
                                <p className="font-medium truncate">{file.name}</p>
                                <span className="text-xs text-muted-foreground">
                                  {(file.size / 1024).toFixed(1)} KB
                                </span>
                              </div>
                            </div>
                            <Button variant="ghost" size="icon" onClick={() => removeFile(index)}>
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        ))}
                      </div>
                      
                      {/* Token usage visualization */}
                      <div className="mt-6 space-y-2">
                        <div className="flex justify-between text-xs text-muted-foreground mb-1">
                          <span>Kontext-Nutzung: {contextPercentage.toFixed(1)}%</span>
                          <span>{contextAvailablePercentage.toFixed(1)}% verfügbar</span>
                        </div>
                        <Progress value={contextPercentage} max={100} className={`h-2 ${
                          contextPercentage > 90 ? 'bg-destructive/20' :
                          contextPercentage > 70 ? 'bg-amber-500/20' :
                          'bg-primary/20'
                        }`} />
                      </div>
                      
                      <div className="flex flex-wrap gap-3 mt-6">
                        <Button 
                          onClick={handleUpload} 
                          disabled={uploadMutation.isPending || files.length === 0 || sessionFiles.length >= 5} 
                          className="flex-1 sm:flex-initial"
                        >
                          {uploadMutation.isPending ? (
                            <>
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              Wird hochgeladen...
                            </>
                          ) : (
                            <>
                              <Upload className="mr-2 h-4 w-4" />
                              Hochladen
                            </>
                          )}
                        </Button>
                        <Button 
                          variant="outline" 
                          onClick={resetUpload} 
                          disabled={uploadMutation.isPending || files.length === 0} 
                          className="flex-1 sm:flex-initial"
                        >
                          Zurücksetzen
                        </Button>
                        <Button 
                          variant="outline"
                          onClick={() => {
                            // Einfache Lösung: Nutze das bereits existierende versteckte Input-Element
                            const fileInput = document.getElementById('file-upload-hidden') as HTMLInputElement;
                            if (fileInput) {
                              fileInput.click();
                            } else {
                              console.error("Konnte das file-upload-hidden Element nicht finden");
                            }
                          }}
                          disabled={uploadMutation.isPending || sessionFiles.length >= 5}
                          className={`flex-1 items-center justify-center ${
                            uploadMutation.isPending || sessionFiles.length >= 5 ? 'opacity-50 cursor-not-allowed' : ''
                          }`}
                        >
                          <FileText className="mr-2 h-4 w-4" />
                          {sessionFiles.length >= 5 ? "Limit erreicht" : "Dateien auswählen"}
                        </Button>
                      </div>
                      
                      {/* Verstecktes Input-Element für Dateiauswahl */}
                      <input 
                        id="file-upload-hidden" 
                        type="file" 
                        multiple 
                        accept=".pdf,.txt" 
                        onChange={handleFileChange} 
                        className="hidden" 
                        disabled={uploadMutation.isPending || sessionFiles.length >= 5}
                      />
                      
                      {error && (
                        <div className="mt-4 p-3 bg-destructive/10 rounded-md border border-destructive/20 text-destructive flex items-start gap-2">
                          <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                          <p className="text-sm">{error}</p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <>
                      <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
                        <Upload className="h-10 w-10 text-primary" />
                      </div>
                      <div className="text-center space-y-2">
                        <h3 className="font-semibold text-lg">Dateien hier ablegen oder auswählen</h3>
                        <p className="text-muted-foreground text-sm max-w-md">
                          Lade bis zu 5 Dateien (PDF, TXT) hoch. Die Dateien werden analysiert und daraus Lernmaterialien erstellt.
                        </p>
                      </div>
                      <Button 
                        className="mt-2 gap-2"
                        onClick={() => {
                          const fileInput = document.getElementById('file-upload-initial') as HTMLInputElement;
                          if (fileInput) {
                            fileInput.click();
                          }
                        }}
                      >
                        <FileText className="h-4 w-4" />
                        Dateien auswählen
                      </Button>
                      <input 
                        id="file-upload-initial" 
                        type="file" 
                        multiple 
                        accept=".pdf,.txt" 
                        onChange={handleFileChange} 
                        className="hidden" 
                      />
                    </>
                  )}
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center p-10 animate-fade-in space-y-4">
                <div className="w-20 h-20 rounded-full bg-green-100 flex items-center justify-center">
                  <CheckCircle className="h-10 w-10 text-green-600" />
                </div>
                <h3 className="text-xl font-semibold">Dateien erfolgreich hochgeladen</h3>
                <p className="text-muted-foreground text-center max-w-md">
                  Deine Dateien wurden analysiert. Du kannst nun mit dem Lernen beginnen oder weitere Dateien hochladen.
                </p>
                <div className="flex gap-3 mt-4">
                  <Button onClick={resetUpload} variant="outline" className="gap-2">
                    <Upload className="h-4 w-4" />
                    Weitere Dateien hochladen
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
          
          {uploadMutation.isPending && (
            <div className="p-4 bg-primary/5 border-t border-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Fortschritt</span>
                <span className="text-sm text-muted-foreground">{Math.round(uploadProgress)}%</span>
              </div>
              <Progress value={uploadProgress} className="h-2" />
            </div>
          )}
          
          <CardFooter className="flex justify-between border-t bg-muted/20 px-6 py-4">
            <div className="text-xs text-muted-foreground">
              <span className="font-medium">Hinweis:</span> Deine Dateien werden sicher gespeichert und nur für die Erstellung von Lernmaterial verwendet.
            </div>
          </CardFooter>
        </Card>
      </div>
    </section>
  );
};

export default ExamUploader;
