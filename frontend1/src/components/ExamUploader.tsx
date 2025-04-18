import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FileText, Upload, CheckCircle, Loader2, X, AlertCircle, BookOpen, CreditCard, RefreshCw } from 'lucide-react';
import { useToast } from "@/hooks/use-toast";
import { useMutation } from '@tanstack/react-query';
import axios from 'axios';
import { Progress } from "@/components/ui/progress";
import { useAuth } from "@/contexts/AuthContext";
import { normalizeUrl, createAuthHeaders, getApiUrl } from "@/lib/api";
import { useTranslation } from 'react-i18next';
import { 
  uploadFileInChunks, 
  resumeFileUpload, 
  getProcessingProgress,
  retryProcessing,
  checkForIncompleteUploads,
  canResumeUpload,
  getResumeData
} from "@/lib/chunkUpload";
import { uploadStatusService, sessionService } from "@/services";

// Verwende relative URL für API-Anfragen, damit der Proxy des Vite-Servers verwendet wird
// const API_URL = import.meta.env.VITE_API_URL || '';

// Maximum context size in tokens
const MAX_CONTEXT_SIZE = 128000; // GPT-4o Kontextgrösse
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
  credits_available?: number;
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
  credits_available?: number;
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
  credits_available?: number;
}

// Interface für den Uploadstatus
interface UploadStatus {
  file: File;
  progress: number;
  status: 'pending' | 'uploading' | 'completed' | 'error';
  sessionId?: string;
  remainingTime?: number;
}

// Eine Funktion zur Schätzung der Token-Anzahl basierend auf der Dateigrösse
const estimateTokensFromFile = async (file: File): Promise<number> => {
  // Kalibrierungsfaktor (empirisch ermittelt) - reduziert die Schätzung, da wir überschätzen
  const CALIBRATION_FACTOR = 0.2; // Reduziert auf 20% für GPT-4o, da wir einen grösseren Kontext haben
  
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
  const { refreshUserCredits } = useAuth();
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
  // Neue State-Variable für den Upload-Fehlerstatus
  const [uploadError, setUploadError] = useState<{
    title: string;
    message: string;
    code?: number;
    type?: string;
  } | null>(null);
  // Neuer State für den Processing-Status nach dem Upload
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [processingProgress, setProcessingProgress] = useState<number>(0);
  const [processingMessage, setProcessingMessage] = useState<string>("");
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const { t } = useTranslation();

  // Aktualisiere die Session-Informationen in regelmässigen Abständen
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
    };
    
    updateTokenEstimate();
  }, [files, existingSessionTokens]);

  const uploadMutation = useMutation({
    mutationFn: async (params: { 
      filesToUpload: File[],
      sessionId?: string,
      onProgress?: (progress: number) => void
    }) => {
      const { filesToUpload, sessionId: initialSessionId, onProgress } = params;

      // Initialisiere Upload-Status für jede Datei
      const uploadStatuses: Record<string, UploadStatus> = {};
      filesToUpload.forEach(file => {
        uploadStatuses[file.name] = {
          file,
          progress: 0,
          status: 'pending'
        };
      });

      // Funktion zum Aktualisieren des Gesamtfortschritts
      const updateProgress = () => {
        const totalProgress = Object.values(uploadStatuses).reduce(
          (sum, status) => sum + status.progress, 
          0
        ) / filesToUpload.length;
        
        if (onProgress) {
          onProgress(totalProgress);
        }
      };

      // Behalte die aktuelle Session-ID bei
      let currentSessionId = initialSessionId;
      
      // Verarbeite jede Datei sequentiell
      for (let i = 0; i < filesToUpload.length; i++) {
        const file = filesToUpload[i];
        const fileStatus = uploadStatuses[file.name];
        
        try {
          // Status aktualisieren
          fileStatus.status = 'uploading';
          updateProgress();
          
          // Lade die Datei in Chunks hoch oder setze einen unterbrochenen Upload fort
          let uploadPromise;
          if (canResumeUpload(file.name)) {
            // Setze unterbrochenen Upload fort
            console.log(`Setze Upload fort für Datei: ${file.name}`);
            uploadPromise = resumeFileUpload(file, {
              sessionId: currentSessionId,
              onProgress: (event) => {
                fileStatus.progress = event.progress;
                fileStatus.remainingTime = event.remainingTime;
                updateProgress();
                console.log(`Fortschritt (Wiederaufnahme) ${file.name}: ${Math.round(event.progress)}% - Chunk ${event.chunkIndex}/${event.totalChunks}`);
              },
              onError: (error, retriesLeft, chunkIndex) => {
                console.warn(`Fehler beim Chunk ${chunkIndex}, ${retriesLeft} Versuche übrig:`, error);
              },
              onRetry: (chunkIndex, attempt) => {
                console.log(`Wiederhole Chunk ${chunkIndex}, Versuch ${attempt}`);
              }
            });
          } else {
            // Starte neuen Upload
            console.log(`Starte neuen Upload für Datei: ${file.name}`);
            uploadPromise = uploadFileInChunks(file, {
              sessionId: currentSessionId,
              onProgress: (event) => {
                fileStatus.progress = event.progress;
                fileStatus.remainingTime = event.remainingTime;
                updateProgress();
                console.log(`Fortschritt (Neu) ${file.name}: ${Math.round(event.progress)}% - Chunk ${event.chunkIndex}/${event.totalChunks}`);
              },
              onError: (error, retriesLeft, chunkIndex) => {
                console.warn(`Fehler beim Chunk ${chunkIndex}, ${retriesLeft} Versuche übrig:`, error);
              },
              onRetry: (chunkIndex, attempt) => {
                console.log(`Wiederhole Chunk ${chunkIndex}, Versuch ${attempt}`);
              }
            });
          }
          
          // Warte auf Abschluss des Uploads
          const sessionId = await uploadPromise;
          
          // Speichere die Session-ID
          if (!currentSessionId && sessionId) {
            currentSessionId = sessionId;
            localStorage.setItem('current_session_id', sessionId);
          }
          
          uploadStatuses[file.name].sessionId = sessionId;
          fileStatus.status = 'completed';
          updateProgress();
        } catch (error) {
          console.error(`Fehler beim Upload von Datei ${file.name}:`, error);
          fileStatus.status = 'error';
          updateProgress();
          throw error;
        }
      }

      console.log(`Upload aller Dateien abgeschlossen für Session: ${currentSessionId}`);
      
      // Wenn alle Dateien hochgeladen wurden, warte auf die Verarbeitungsergebnisse
      if (!currentSessionId) {
        throw new Error("Keine Session-ID erhalten. Upload gescheitert.");
      }
      
      // Da wir in onSuccess auch auf den Upload-Status warten werden,
      // können wir hier einfach die Basisdaten zurückgeben
      return {
        success: true, 
        message: "Dateien hochgeladen, Verarbeitung läuft...",
        session_id: currentSessionId,
        flashcards: [],  // Diese werden erst nach Verarbeitung verfügbar sein
        questions: []    // Diese werden erst nach Verarbeitung verfügbar sein
      };
    },
    
    onSuccess: (data: UploadResponse) => {
      setIsUploaded(true);
      
      if (data.credits_available !== undefined) {
        const storedUser = localStorage.getItem('exammaster_user');
        if (storedUser) {
          try {
            const parsedUser = JSON.parse(storedUser);
            parsedUser.credits = data.credits_available;
            localStorage.setItem('exammaster_user', JSON.stringify(parsedUser));
          } catch (error) {
            console.error('Fehler beim Aktualisieren der Credits:', error);
          }
        }
      }
      
      // Kredite aktualisieren
      refreshUserCredits();
      
      // Der sequentielle Prozess verhindert konkurrierende API-Aufrufe
      if (!data.session_id) {
        toast({
          title: "Fehler",
          description: "Keine Session-ID erhalten. Bitte versuche es später erneut.",
          variant: "destructive",
        });
        return;
      }
      
      // Speichere die Session-ID
      localStorage.setItem('current_session_id', data.session_id);
      
      // Benachrichtigung über erfolgreichen Upload
      toast({
        title: "Dateien hochgeladen",
        description: `${files.length} Datei${files.length > 1 ? 'en wurden' : ' wurde'} erfolgreich hochgeladen. Die Analyse läuft...`,
      });
      
      // Überwache den Upload-Status und führe Aktionen nach Abschluss durch
      let statusPollingInterval = checkUploadStatus(
        data.session_id,
        30,
        (completedSessionId) => {
          // Wenn der Status "completed" ist, lade die Themen
          if (loadTopicsMutation) {
            loadTopicsMutation.mutate(completedSessionId, {
              onSuccess: (topicsData) => {
                console.log("Themen erfolgreich geladen:", topicsData);
                
                // Überprüfe das Format der Daten
                if (!topicsData) {
                  console.error("Keine Daten von loadTopicsMutation zurückgegeben");
                  toast({
                    title: "Unvollständige Daten",
                    description: "Es wurden unvollständige Daten vom Server zurückgegeben. Seite wird neu geladen...",
                    variant: "destructive",
                  });
                  
                  // Verzögerte Neuladen der Seite als Fallback
                  setTimeout(() => window.location.reload(), 3000);
                  return;
                }
                
                // Validiere die zurückgegebenen Daten auf grundlegende Struktur
                try {
                  // Prüfe, ob die grundlegenden Eigenschaften vorhanden sind
                  if (!Array.isArray(topicsData.flashcards)) topicsData.flashcards = [];
                  if (!Array.isArray(topicsData.test_questions)) topicsData.test_questions = [];
                  
                  // Stelle sicher, dass analysis als Objekt existiert
                  if (!topicsData.analysis || typeof topicsData.analysis !== 'object') {
                    topicsData.analysis = { main_topic: "Unbekanntes Thema", subtopics: [] };
                  }
                  
                  // Stelle sicher, dass connections als Array existiert (wenn nötig)
                  if (topicsData.connections && !Array.isArray(topicsData.connections)) {
                    topicsData.connections = [];
                  }
                  
                  // Stelle sicher, dass topics existiert (wenn nötig)
                  if (topicsData.topics && typeof topicsData.topics !== 'object') {
                    topicsData.topics = null;
                  }
                  
                  console.log("Datenstruktur validiert und bereinigt:", topicsData);
                } catch (validationError) {
                  console.error("Fehler bei der Datenvalidierung:", validationError);
                }
                
                // Erstelle ein erweitertes Ergebnisobjekt mit den vollständigen Daten
                const enhancedData = {
                  ...data,
                  flashcards: topicsData.flashcards || [],
                  questions: topicsData.test_questions || [],
                  adaptedData: topicsData
                };
                
                // Log-Ausgabe sicherstellen
                console.log("Erweiterte Daten erstellt:", JSON.stringify({
                  session_id: enhancedData.session_id,
                  flashcards_length: enhancedData.flashcards.length,
                  questions_length: enhancedData.questions.length,
                  topics: enhancedData.adaptedData.topics ? "vorhanden" : "fehlt"
                }));
                
                // Erst nachdem die Themen erfolgreich geladen wurden, 
                // benachrichtige die übergeordnete Komponente mit den erweiterten Daten
                if (onUploadSuccess) {
                  console.log("Rufe onUploadSuccess auf mit erweiterten Daten");
                  onUploadSuccess(enhancedData);
                }
                
                toast({
                  title: "Analyse abgeschlossen",
                  description: "Die Dateien wurden erfolgreich analysiert und stehen jetzt zur Verfügung.",
                });
              },
              onError: (error) => {
                // Detailliertes Logging des Fehlers
                console.error('Vollständiger Fehler beim Laden der Themen:', error);
                
                if (error.response) {
                  console.error('Fehler-Response-Daten:', error.response.data);
                  console.error('Fehler-Status:', error.response.status);
                }
                
                if (error.message) {
                  console.error('Fehlermeldung:', error.message);
                }
                
                // Detaillierter Error-Stack, falls vorhanden
                if (error.stack) {
                  console.error('Fehler-Stack:', error.stack);
                }
                
                // Detaillierte Fehlerbeschreibung im Toast
                const toastRef = toast({
                  title: "Fehler beim Laden der Themen",
                  description: `Die Themen konnten nicht geladen werden: ${error?.message || 'Unbekannter Fehler'}. Sie können es erneut versuchen oder die Seite neu laden.`,
                  variant: "destructive",
                  duration: 0 // Toast bleibt bestehen, bis der Benutzer aktiv wird
                });
                
                // Erstelle einen Button-Container für den Toast
                setTimeout(() => {
                  const toastElement = document.querySelector(`[data-toast-id="${toastRef.id}"] .toast-description`);
                  if (toastElement) {
                    // Container für die Buttons
                    const buttonContainer = document.createElement('div');
                    buttonContainer.className = 'flex gap-2 mt-4';
                    
                    // Button zum Neuladen der Seite
                    const reloadButton = document.createElement('button');
                    reloadButton.innerText = 'Seite neu laden';
                    reloadButton.className = 'bg-primary text-white px-4 py-2 rounded';
                    reloadButton.onclick = () => window.location.reload();
                    
                    // Button zum erneuten Versuchen
                    const retryButton = document.createElement('button');
                    retryButton.innerText = 'Erneut versuchen';
                    retryButton.className = 'bg-secondary text-white px-4 py-2 rounded';
                    retryButton.onclick = () => {
                      // Toast schließen
                      const closeButton = document.querySelector(`[data-toast-id="${toastRef.id}"] button[aria-label="Close"]`);
                      if (closeButton && 'click' in closeButton) {
                        (closeButton as HTMLButtonElement).click();
                      }
                      
                      // Erneut versuchen, nach kurzer Verzögerung
                      setTimeout(() => {
                        if (loadTopicsMutation) {
                          loadTopicsMutation.mutate(completedSessionId);
                        }
                      }, 1000);
                    };
                    
                    // Buttons zum Container hinzufügen
                    buttonContainer.appendChild(retryButton);
                    buttonContainer.appendChild(reloadButton);
                    
                    // Container zum Toast hinzufügen
                    toastElement.appendChild(buttonContainer);
                  }
                }, 100); // Kurze Verzögerung, um sicherzustellen, dass der Toast gerendert wurde
                
                // Als Fallback die übergeordnete Komponente trotzdem benachrichtigen,
                // aber nicht automatisch die Seite neuladen
                if (onUploadSuccess) {
                  onUploadSuccess(data);
                }
              }
            });
          } else {
            // Falls loadTopicsMutation nicht verfügbar ist
            if (onUploadSuccess) onUploadSuccess(data);
          }
        },
        // Fehlerbehandlung für den Status-Check als Parameter übergeben
        (error) => {
          console.error("Fehler beim Abrufen des Upload-Status:", error);
          toast({
            title: "Fehler bei der Verarbeitung",
            description: "Die Verarbeitung konnte nicht abgeschlossen werden. Bitte versuche es später erneut.",
            variant: "destructive"
          });
        }
      );
    },
    
    onError: (error) => {
      console.error('Upload error:', error);
      setError(error.message || 'Ein unerwarteter Fehler ist aufgetreten');
      setIsUploaded(false);
      setUploadProgress(0);
      
      toast({
        title: "Fehler beim Upload",
        description: error.message || 'Ein unerwarteter Fehler ist aufgetreten',
        variant: "destructive",
      });
    }
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
    if (files.length === 0) {
      toast({
        title: t('uploader.noFilesSelected'),
        description: t('uploader.pleaseSelectFiles'),
        variant: "destructive",
      });
      setIsProcessing(false); // Ladebildschirm deaktivieren, falls keine Dateien da sind
      return;
    }
    
    setUploadProgress(0);
    setIsUploaded(false);
    setError(null);
    setUploadError(null);
    
    // Upload-Funktion
    const uploadWithProgress = async () => {
      try {
        // Ein oder mehrere Dateien verarbeiten
        let currentSessionId = sessionId; // Verwende die vorhandene SessionId, falls vorhanden
        let currentSessionData = {
          success: true,
          message: "Dateien hochgeladen, Verarbeitung läuft...",
          session_id: currentSessionId || "",
          flashcards: [],
          questions: []
        };
        
        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          setUploadProgress(0); // Für jede neue Datei den Fortschritt zurücksetzen
          setProcessingMessage(`Datei ${i+1} von ${files.length} wird hochgeladen: ${file.name}`);
          
          // Konfiguriere Upload-Optionen
          const uploadOptions = {
            sessionId: currentSessionId,
            onProgress: (event: any) => {
              const uploadProgress = event.progress;
              // Bei mehreren Dateien: Gewichteter Fortschritt (50% für Upload)
              const overallProgress = i * (50/files.length) + (uploadProgress * (50/files.length));
              setProcessingProgress(overallProgress);
              setUploadProgress(event.progress);
              
              if (!currentSessionId && event.sessionId) {
                currentSessionId = event.sessionId;
                currentSessionData.session_id = event.sessionId;
              }
            },
            onError: (error: Error, retriesLeft: number, chunkIndex: number) => {
              console.error(`Upload-Fehler: ${error.message}. Verbleibende Versuche: ${retriesLeft}`);
              
              if (retriesLeft === 0) {
                setUploadError({
                  title: t('uploader.uploadFailed'),
                  message: `${t('uploader.errorChunk')} ${chunkIndex}: ${error.message}`,
                  code: 500,
                  type: 'upload'
                });
                setIsProcessing(false); // Bei Fehler Ladebildschirm ausblenden
              }
            },
            onRetry: (chunkIndex: number, attempt: number) => {
              console.log(`Versuche erneut, Chunk ${chunkIndex} hochzuladen (Versuch ${attempt})`);
              
              toast({
                title: t('uploader.retryingUpload'),
                description: `${t('uploader.retryingChunk')} ${chunkIndex} (${t('uploader.attempt')} ${attempt})`,
                variant: "default",
              });
            }
          };
          
          try {
            // Lade Datei in Chunks hoch
            const uploadedSessionId = await uploadFileInChunks(file, uploadOptions);
            
            // Aktualisiere die Session-ID
            if (uploadedSessionId) {
              currentSessionId = uploadedSessionId;
              currentSessionData.session_id = uploadedSessionId;
            }
            
            if (i === files.length - 1) {
              // Letzte Datei wurde hochgeladen
              setIsUploaded(true);
              setProcessingMessage("Upload abgeschlossen. Verarbeitung läuft...");
              setProcessingProgress(50); // Upload ist 50% des Gesamtprozesses
              
              try {
                // Verwende den uploadStatusService für die Statusüberwachung
                if (currentSessionId) {
                  toast({
                    title: "Upload abgeschlossen",
                    description: "Dateien wurden hochgeladen und werden jetzt verarbeitet...",
                  });
                  
                  console.log("Upload abgeschlossen, starte Statusüberwachung für Session:", currentSessionId);
                  
                  // Polling für Verarbeitungsfortschritt starten
                  const progressInterval = setInterval(async () => {
                    try {
                      const progress = await getProcessingProgress(currentSessionId);
                      if (progress.success) {
                        // Skaliere den Fortschritt für die zweite Hälfte (50-100%)
                        const scaledProgress = 50 + ((progress.progress || 0) / 2);
                        setProcessingProgress(scaledProgress);
                        
                        if (progress.status === 'completed') {
                          clearInterval(progressInterval);
                          setProcessingProgress(100);
                          setProcessingMessage("Verarbeitung abgeschlossen!");
                        } else if (progress.message) {
                          setProcessingMessage(progress.message);
                        }
                      }
                    } catch (e) {
                      console.error("Fehler beim Abrufen des Fortschritts:", e);
                    }
                  }, 2000);
                  
                  // Speichere das Interval in der Ref
                  progressIntervalRef.current = progressInterval;
                  
                  // Überwache den Status und lade Daten, wenn der Upload abgeschlossen ist
                  uploadStatusService.checkUploadStatusAndLoadData(currentSessionId)
                    .then((studyData) => {
                      if (progressIntervalRef.current) {
                        clearInterval(progressIntervalRef.current);
                        progressIntervalRef.current = null;
                      }
                      setIsProcessing(false);
                      console.log("Daten erfolgreich geladen:", studyData);
                      
                      // Sitzungs-ID im sessionService speichern
                      sessionService.setCurrentSessionId(currentSessionId);
                      
                      // Wenn loadTopicsMutation verfügbar ist, rufe es auf
                      if (loadTopicsMutation) {
                        console.log("Rufe loadTopicsMutation auf für Session:", currentSessionId);
                        loadTopicsMutation.mutate(currentSessionId);
                      }
                      
                      // Benachrichtige die übergeordnete Komponente, wenn vorhanden
                      if (onUploadSuccess) {
                        console.log("Rufe onUploadSuccess auf mit erweiterten Daten");
                        const enhancedData = {
                          ...currentSessionData,
                          flashcards: studyData.flashcards || [],
                          questions: studyData.testQuestions || []
                        };
                        onUploadSuccess(enhancedData);
                      }
                      
                      toast({
                        title: "Analyse abgeschlossen",
                        description: "Die Dateien wurden erfolgreich analysiert und stehen jetzt zur Verfügung.",
                      });
                    })
                    .catch((error) => {
                      console.error("Fehler beim Überwachen des Upload-Status:", error);
                      
                      toast({
                        title: "Fehler",
                        description: `Fehler beim Verarbeiten der Dateien: ${error.message}`,
                        variant: "destructive",
                      });
                    });
                }
              } catch (error) {
                console.error("Fehler beim Starten der Statusüberwachung:", error);
                
                toast({
                  title: "Fehler",
                  description: "Beim Starten der Statusüberwachung ist ein Fehler aufgetreten.",
                  variant: "destructive",
                });
              }
            }
          } catch (uploadError) {
            console.error(`Fehler beim Hochladen von ${file.name}:`, uploadError);
            
            // Bei Fehler Ladebildschirm ausblenden
            setIsProcessing(false);
            
            // Fehler für die UI anzeigen
            setUploadError({
              title: t('uploader.uploadFailed'),
              message: uploadError instanceof Error 
                ? uploadError.message 
                : t('uploader.unknownError'),
              code: 500,
              type: 'upload'
            });
            
            return; // Beende den Upload bei einem Fehler
          }
        }
      } catch (error) {
        console.error("Upload-Prozess fehlgeschlagen:", error);
        
        // Bei Fehler Ladebildschirm ausblenden
        setIsProcessing(false);
        
        // Fehler für die UI anzeigen
        setUploadError({
          title: t('uploader.uploadProcessFailed'),
          message: error instanceof Error 
            ? error.message 
            : t('uploader.unknownError'),
          code: 500,
          type: 'process'
        });
      }
    };
    
    // Starte den Upload-Prozess
    uploadWithProgress();
  };

  const handleRetry = () => {
    // Wenn es Dateien gibt, versuche erneut
    if (files.length > 0) {
      handleUpload();
      return;
    }
    
    // Wenn es eine Session gibt, versuche die Verarbeitung neu zu starten
    if (sessionId) {
      toast({
        title: "Verarbeitung wird neu gestartet",
        description: "Die Verarbeitung für die hochgeladenen Dateien wird neu gestartet.",
        variant: "default",
      });
      
      // Setze den Fortschritt zurück
      setUploadProgress(0);
      
      // Sende eine Anfrage zum Neustart der Verarbeitung
      retryProcessing(sessionId)
        .then(response => {
          if (response.success) {
            toast({
              title: "Verarbeitung neu gestartet",
              description: "Die Verarbeitung wurde erfolgreich neu gestartet. Bitte warte einen Moment.",
              variant: "default",
            });
            
            // Starte das Polling für den Fortschritt
            const pollProgressInterval = setInterval(async () => {
              try {
                const progress = await getProcessingProgress(sessionId);
                if (progress.success) {
                  // Aktualisiere den Fortschritt (50% für Upload, 50% für Verarbeitung)
                  setUploadProgress(50 + (progress.progress / 2));
                  
                  // Bei Fertigstellung
                  if (progress.status === 'completed') {
                    clearInterval(pollProgressInterval);
                    // Lade die Ergebnisse
                    loadTopicsMutation?.mutate(sessionId);
                    setIsUploaded(true);
                  }
                  
                  // Bei Fehler
                  if (progress.status === 'failed' || progress.status === 'error') {
                    clearInterval(pollProgressInterval);
                    setError(progress.message || "Ein Fehler ist während der Verarbeitung aufgetreten");
                    setUploadProgress(0);
                  }
                }
              } catch (e) {
                console.error("Fehler beim Abrufen des Fortschritts:", e);
              }
            }, 5000);
            
            // Stoppe das Polling nach 5 Minuten, falls es nicht abgeschlossen wird
            setTimeout(() => {
              clearInterval(pollProgressInterval);
            }, 300000);
          } else {
            toast({
              title: "Neustart fehlgeschlagen",
              description: response.message || "Die Verarbeitung konnte nicht neu gestartet werden.",
              variant: "destructive",
            });
          }
        })
        .catch(error => {
          toast({
            title: "Fehler beim Neustart",
            description: error?.message || "Ein unbekannter Fehler ist aufgetreten.",
            variant: "destructive",
          });
        });
    }
  };

  // Nachdem die Komponente geladen ist, nach unterbrochenen Uploads suchen
  useEffect(() => {
    const incompleteUploads = checkForIncompleteUploads();
    
    if (incompleteUploads.length > 0) {
      // Nach Zeitstempel sortieren (neueste zuerst)
      incompleteUploads.sort((a, b) => b.timestamp - a.timestamp);
      
      // Nur die 3 neuesten anzeigen
      const recentUploads = incompleteUploads.slice(0, 3);
      const fileNames = recentUploads.map(upload => upload.fileName).join(", ");
      
      toast({
        title: "Unterbrochene Uploads gefunden",
        description: `${recentUploads.length} unterbrochene Upload(s) gefunden: ${fileNames}. Möchtest du diese Dateien erneut hochladen?`,
        variant: "default",
        duration: 10000,
        action: (
          <Button 
            variant="default" 
            size="sm" 
            onClick={() => {
              // Zeige dem Benutzer eine Auswahl an Dateien, die fortgesetzt werden können
              // Hier müsste eine UI-Komponente hinzugefügt werden
              toast({
                title: "Unterbrochene Uploads",
                description: "Bitte wähle die entsprechenden Dateien erneut aus, um den Upload fortzusetzen.",
                variant: "default",
              });
            }}
          >
            Fortsetzen
          </Button>
        )
      });
    }
  }, []);

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

  // Funktion zum Abrufen der Session-Informationen
  const fetchExistingSessionTokens = async (sessionId: string) => {
    if (!sessionId) return;
    
    setIsLoadingSessionInfo(true);
    
    try {
      // API-Aufruf, um Informationen zur Session abzurufen
      const response = await sessionService.getSessionInfo(sessionId);
      
      if (response.success && response.data) {
        // Aktualisiere die Tokens und Dateien aus der Session
        setExistingSessionTokens(response.data.token_count || 0);
        setSessionFiles(response.data.files || []);
      }
    } catch (error) {
      console.error("Fehler beim Abrufen der Session-Informationen:", error);
    } finally {
      setIsLoadingSessionInfo(false);
    }
  };

  return (
    <div className="relative w-full space-y-4">
      <section id="upload" className="section-container">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12 space-y-4">
            <h2 className="text-3xl md:text-4xl font-bold animate-fade-in">
              {t('uploader.title')}
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto animate-fade-in">
              {t('uploader.subtitle')}
            </p>
          </div>
          
          <Card className="border border-border/50 shadow-soft overflow-hidden animate-slide-up relative">
            <CardHeader className="pb-4">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    {t('uploader.title')}
                  </CardTitle>
                  <CardDescription>
                    {t('uploader.subtitle')}
                  </CardDescription>
                  {sessionId && (
                    <div className="text-xs text-muted-foreground mt-1">
                      {isLoadingSessionInfo ? (
                        <span className="flex items-center">
                          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                          {t('uploader.loadingSessionInfo')}
                        </span>
                      ) : existingSessionTokens > 0 ? (
                        <div className="space-y-1">
                          {sessionFiles.length >= 5 && (
                            <span className="flex items-center text-xs text-amber-500 font-medium ml-4">
                              <span className="inline-block w-3 h-3 rounded-full bg-amber-500/30 mr-1"></span>
                              {t('uploader.maxFilesReached')}
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
                        const authToken = localStorage.getItem('exammaster_token');
                        console.log(`Session zurücksetzen: POST /api/v1/session/reset für Session ${sessionId}`);
                        fetch(getApiUrl('api/v1/session/reset'), {
                          method: 'POST',
                          headers: {
                            'Content-Type': 'application/json',
                            'Authorization': authToken ? `Bearer ${authToken}` : ''
                          },
                          credentials: 'include',
                          body: JSON.stringify({ session_id: sessionId })
                        }).catch(() => {});
                      } catch (error) {
                        // Fehler ignorieren
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
                    {t('uploader.newSession')}
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
                              Gesamtgrösse: {isEstimating ? "Wird berechnet..." : getTokensDisplay()}
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
                            onClick={() => {
                              // Sofort Ladebildschirm anzeigen
                              setIsProcessing(true);
                              setProcessingMessage("Deine Dateien werden hochgeladen...");
                              setProcessingProgress(0);
                              handleUpload();
                            }} 
                            disabled={uploadMutation.isPending || files.length === 0 || sessionFiles.length >= 5 || isProcessing} 
                            className="flex-1 sm:flex-initial"
                          >
                            {uploadMutation.isPending || isProcessing ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                {isProcessing ? "Verarbeitung läuft..." : t('uploader.uploading')}
                              </>
                            ) : (
                              <>
                                <Upload className="mr-2 h-4 w-4" />
                                {t('uploader.uploadButton')}
                              </>
                            )}
                          </Button>
                          <Button 
                            variant="outline" 
                            onClick={resetUpload} 
                            disabled={uploadMutation.isPending || files.length === 0} 
                            className="flex-1 sm:flex-initial"
                          >
                            {t('uploader.resetButton')}
                          </Button>
                          <Button 
                            variant="outline"
                            onClick={() => {
                              // Einfache Lösung: Nutze das bereits existierende versteckte Input-Element
                              const fileInput = document.getElementById('file-upload-hidden') as HTMLInputElement;
                              if (fileInput) {
                                fileInput.click();
                              }
                            }}
                            disabled={uploadMutation.isPending || sessionFiles.length >= 5}
                            className={`flex-1 items-center justify-center ${
                              uploadMutation.isPending || sessionFiles.length >= 5 ? 'opacity-50 cursor-not-allowed' : ''
                            }`}
                          >
                            <FileText className="mr-2 h-4 w-4" />
                            {sessionFiles.length >= 5 ? t('uploader.limitReached') : t('uploader.selectFiles')}
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
                          <div className="mt-4 p-3 bg-destructive/10 rounded-md border border-destructive/20 text-destructive flex flex-col items-start gap-2">
                            <div className="flex items-start gap-2 w-full">
                              <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                              <p className="text-sm">{error}</p>
                            </div>
                            {error.includes("Nicht genügend Credits") && (
                              <Button 
                                variant="default" 
                                className="mt-2 self-end" 
                                onClick={() => window.location.href = "/payment"}
                              >
                                <CreditCard className="mr-2 h-4 w-4" />
                                Credits aufladen
                              </Button>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <>
                        <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
                          <Upload className="h-8 w-8 text-primary" />
                        </div>
                        <div className="text-center space-y-2">
                          <h3 className="font-medium text-lg">{t('uploader.dropzone')}</h3>
                          <p className="text-sm text-muted-foreground">{t('uploader.dropzoneDescription')}</p>
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
                          {t('uploader.selectFiles')}
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
              ) : isProcessing ? (
                <div className="flex flex-col items-center justify-center p-10 animate-fade-in space-y-6">
                  <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
                    <Loader2 className="h-10 w-10 text-primary animate-spin" />
                  </div>
                  <div className="text-center space-y-2">
                    <h3 className="text-xl font-semibold">Verarbeitung läuft</h3>
                    <p className="text-muted-foreground max-w-md">
                      {processingMessage}
                    </p>
                  </div>
                  
                  <div className="w-full max-w-md space-y-2">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Fortschritt</span>
                      <span>{Math.round(processingProgress)}%</span>
                    </div>
                    <Progress value={processingProgress} max={100} className="h-2" />
                  </div>
                  
                  <p className="text-xs text-muted-foreground text-center max-w-md mt-4">
                    Bitte warte, während wir deine Dateien verarbeiten. Dies kann je nach Größe und Komplexität einige Minuten dauern.
                  </p>
                  
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => {
                      // Abbrechen des Upload/Verarbeitungsprozesses
                      if (progressIntervalRef.current) {
                        clearInterval(progressIntervalRef.current);
                        progressIntervalRef.current = null;
                      }
                      setIsProcessing(false);
                      setFiles([]);
                      toast({
                        title: "Vorgang abgebrochen",
                        description: "Der Upload- und Verarbeitungsprozess wurde abgebrochen.",
                        variant: "default",
                      });
                    }}
                    className="mt-2"
                  >
                    Abbrechen
                  </Button>
                </div>
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
    </div>
  );
};

export default ExamUploader;