import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileText, Upload, CheckCircle, Loader2, RotateCw, ChevronLeft, ChevronRight } from 'lucide-react';
import { useToast } from "@/components/ui/use-toast";
import { Progress } from "@/components/ui/progress";
import * as uploadService from "@/lib/api/uploadService";
import { Flashcard, Question, Topic, UploadResults, UploadApiResponse } from "@/types";

interface ExamUploaderProps {
  onUploadComplete: (sessionId: string) => void;
}

const FlashcardView = ({ flashcards }: { flashcards: Flashcard[] }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);

  const handleNext = () => {
    if (currentIndex < flashcards.length - 1) {
      setCurrentIndex(currentIndex + 1);
      setFlipped(false);
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
      setFlipped(false);
    }
  };

  if (flashcards.length === 0) {
    return <div className="text-center py-8">Keine Karteikarten gefunden</div>;
  }

  return (
    <div className="mx-auto max-w-md py-4">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>Karteikarte {currentIndex + 1} von {flashcards.length}</CardTitle>
        </CardHeader>
        <CardContent>
          <div 
            className="relative min-h-[200px] rounded-lg border p-4 cursor-pointer transition-all duration-300"
            onClick={() => setFlipped(!flipped)}
          >
            {!flipped ? (
              <div className="flex justify-center items-center h-full">
                <p className="text-lg font-medium">{flashcards[currentIndex].question}</p>
              </div>
            ) : (
              <div className="flex justify-center items-center h-full">
                <p>{flashcards[currentIndex].answer}</p>
              </div>
            )}
          </div>
          <div className="text-center text-sm text-muted-foreground mt-2">
            Klicken zum Umdrehen
          </div>
        </CardContent>
        <CardFooter className="flex justify-between">
          <Button variant="outline" onClick={handlePrev} disabled={currentIndex === 0}>
            <ChevronLeft className="mr-1 h-4 w-4" />
            Zurück
          </Button>
          <Button onClick={handleNext} disabled={currentIndex === flashcards.length - 1}>
            Weiter
            <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
};

const TopicsView = ({ topics }: { topics: { main_topic: { name: string }, subtopics: Topic[] } }) => {
  return (
    <div className="py-4">
      <h3 className="text-xl font-bold mb-4">Hauptthema: {topics.main_topic.name}</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {topics.subtopics.map((topic) => (
          <Card key={topic.id}>
            <CardHeader className="py-4">
              <CardTitle className="text-lg">{topic.name}</CardTitle>
            </CardHeader>
            {topic.description && (
              <CardContent>
                <p className="text-sm text-muted-foreground">{topic.description}</p>
              </CardContent>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
};

const QuestionsView = ({ questions }: { questions: Question[] }) => {
  return (
    <div className="py-4">
      <h3 className="text-xl font-bold mb-4">Testfragen</h3>
      <div className="space-y-6">
        {questions.map((question, index) => (
          <Card key={question.id}>
            <CardHeader>
              <CardTitle className="text-lg">Frage {index + 1}</CardTitle>
              <CardDescription>{question.text}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {question.options.map((option, optIndex) => (
                  <div 
                    key={optIndex}
                    className={`p-3 rounded-lg border ${
                      option === question.correct_answer ? 'border-green-500 bg-green-50 dark:bg-green-900/20' : 'border-gray-200'
                    }`}
                  >
                    {option}
                    {option === question.correct_answer && (
                      <div className="mt-1 text-sm text-green-600 dark:text-green-400">
                        ✓ Richtige Antwort
                      </div>
                    )}
                  </div>
                ))}
                {question.explanation && (
                  <div className="mt-4 text-sm text-muted-foreground">
                    <strong>Erklärung:</strong> {question.explanation}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

const ExamUploader: React.FC<ExamUploaderProps> = ({ onUploadComplete }) => {
  const { toast } = useToast();
  const [files, setFiles] = useState<File[] | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [results, setResults] = useState<UploadResults | null>(null);
  const [activeView, setActiveView] = useState<'upload' | 'processing' | 'results'>('upload');
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);
  
  // Maximum context size in tokens (this is an example value, adjust as needed)
  const MAX_CONTEXT_SIZE = 500000;
  const [contextUsage, setContextUsage] = useState(0);

  // Effekt für das Polling des Verarbeitungsstatus
  useEffect(() => {
    if (sessionId && isProcessing) {
      const interval = setInterval(async () => {
        try {
          const statusResult = await uploadService.checkUploadStatus(sessionId);
          
          // Wenn die Verarbeitung abgeschlossen oder fehlgeschlagen ist
          if (statusResult.processing_status === 'completed') {
            clearInterval(interval);
            setIsProcessing(false);
            fetchResults();
          } else if (statusResult.processing_status === 'error') {
            clearInterval(interval);
            setIsProcessing(false);
            toast({
              title: "Fehler bei der Verarbeitung",
              description: statusResult.error_message || "Die Datei konnte nicht verarbeitet werden.",
              variant: "destructive"
            });
          } else {
            // Aktualisiere den Fortschritt, falls verfügbar
            if (statusResult.processing_progress) {
              setProcessingProgress(statusResult.processing_progress * 100);
            }
          }
        } catch (error) {
          console.error("Fehler beim Abrufen des Status:", error);
        }
      }, 3000); // Alle 3 Sekunden
      
      setPollingInterval(interval);
      
      return () => {
        if (interval) clearInterval(interval);
      };
    }
  }, [sessionId, isProcessing, toast]);

  // Bereinige das Intervall beim Unmounten
  useEffect(() => {
    return () => {
      if (pollingInterval) clearInterval(pollingInterval);
    };
  }, [pollingInterval]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (selectedFiles && selectedFiles.length > 0) {
      const validFiles: File[] = [];
      let totalSize = 0;
      for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i];
        if (file.type === 'application/pdf' || 
            file.type === 'application/msword' ||
            file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
            file.type === 'text/plain') {
          validFiles.push(file);
          totalSize += file.size;
        } else {
          toast({
            title: "Ungültiges Format übersprungen",
            description: `Datei ${file.name} hat ein nicht unterstütztes Format.`,
          });
        }
      }
      
      if (validFiles.length > 0) {
        setFiles(validFiles);
        const estimatedTokens = Math.min(Math.round((totalSize / 1024) * 150), MAX_CONTEXT_SIZE);
        setContextUsage(estimatedTokens);
      } else {
         // Wenn nach Filterung keine gültigen Dateien übrig sind
         setFiles(null);
         setContextUsage(0);
         toast({
             title: "Keine gültigen Dateien",
             description: "Bitte nur PDF, DOC, DOCX oder TXT-Dateien auswählen.",
             variant: "destructive",
           });
      }
    }
  };

  const handleUpload = async () => {
    // Prüfe, ob `files` ein Array ist und Elemente enthält
    if (!files || files.length === 0) return;
    
    setIsUploading(true);
    
    try {
      // Übergebe das `files`-Array an den Service
      const uploadResponse = await uploadService.uploadFiles(files);
      
      // Verwende session_id und upload_id aus der neuen Antwortstruktur
      setSessionId(uploadResponse.session_id);
      setIsUploading(false);
      setIsProcessing(true);
      setActiveView('processing');
      
      toast({
        title: `${uploadResponse.files.length} Datei(en) hochgeladen`, // Angepasste Meldung
        description: "Deine Dateien werden jetzt verarbeitet...",
      });
      
      if (onUploadComplete && uploadResponse.session_id) {
        onUploadComplete(uploadResponse.session_id);
      }
    } catch (error) {
      console.error("Fehler beim Hochladen:", error);
      setIsUploading(false);
      
      toast({
        title: "Upload fehlgeschlagen",
        description: "Beim Hochladen der Dateien ist ein Fehler aufgetreten.", // Plural
        variant: "destructive",
      });
    }
  };

  const fetchResults = async () => {
    if (sessionId) {
      try {
        const data = await uploadService.getUploadResults(sessionId);
        setResults(data);
        setActiveView('results');
        
        toast({
          title: "Verarbeitung abgeschlossen",
          description: "Deine Lernmaterialien wurden erfolgreich erstellt.",
        });
      } catch (error) {
        console.error("Fehler beim Abrufen der Ergebnisse:", error);
        toast({
          title: "Fehler beim Abrufen der Ergebnisse",
          description: "Die Ergebnisse konnten nicht geladen werden. Bitte versuche es später erneut.",
          variant: "destructive"
        });
      }
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    
    if (e.dataTransfer.files.length > 0) {
      const droppedFiles = Array.from(e.dataTransfer.files);
      const validFiles: File[] = [];
      let totalSize = 0;

      for (const file of droppedFiles) {
          if (file.type === 'application/pdf' || 
              file.type === 'application/msword' ||
              file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
              file.type === 'text/plain') {
            validFiles.push(file);
            totalSize += file.size;
          } else {
            toast({
              title: "Ungültiges Format übersprungen",
              description: `Datei ${file.name} hat ein nicht unterstütztes Format.`,
            });
          }
      }

      if (validFiles.length > 0) {
        setFiles(validFiles);
        const estimatedTokens = Math.min(Math.round((totalSize / 1024) * 150), MAX_CONTEXT_SIZE);
        setContextUsage(estimatedTokens);
      } else {
         setFiles(null);
         setContextUsage(0);
         toast({
             title: "Keine gültigen Dateien",
             description: "Bitte nur PDF, DOC, DOCX oder TXT-Dateien per Drag & Drop ziehen.",
             variant: "destructive",
           });
      }
    }
  };

  const resetUpload = () => {
    setFiles(null); // Geändert von setFile
    setContextUsage(0);
    setActiveView('upload');
    setResults(null);
    setSessionId(null);
    setIsProcessing(false);
    setProcessingProgress(0);
  };

  // Calculate percentage of context used
  const contextPercentage = (contextUsage / MAX_CONTEXT_SIZE) * 100;
  const contextAvailablePercentage = 100 - contextPercentage;
  
  const renderUploadView = () => (
    <div 
      className={`p-8 border-2 border-dashed rounded-lg flex flex-col items-center justify-center gap-4 transition-all ${
        files && files.length > 0 ? 'border-primary/50 bg-primary/5' : 'border-border hover:border-primary/30 hover:bg-secondary/50'
      }`}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {files && files.length > 0 ? (
        <div className="flex flex-col items-center gap-3 animate-fade-in w-full">
          <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
            <FileText className="h-8 w-8 text-primary" />
          </div>
          <div className="text-center">
            {/* Zeige Anzahl und Namen der ersten paar Dateien */} 
            <p className="font-medium">
              {files.length} Datei(en) ausgewählt
            </p>
            <p className="text-sm text-muted-foreground truncate max-w-xs">
              {files.map(f => f.name).slice(0, 3).join(', ')}{files.length > 3 ? '...' : ''}
            </p>
             <p className="text-sm text-muted-foreground">
               Gesamtgröße: {(files.reduce((sum, f) => sum + f.size, 0) / 1024 / 1024).toFixed(2)} MB
            </p>
          </div>
          
          <div className="w-full max-w-md mt-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Geschätzter API Kontext Verbrauch:</span>
              <span className={contextPercentage > 90 ? 'text-destructive font-medium' : 'font-medium'}>
                {contextUsage} / {MAX_CONTEXT_SIZE} Tokens
              </span>
            </div>
            <Progress value={contextPercentage} className="h-2" />
            <p className="text-xs text-muted-foreground text-right">
              {contextAvailablePercentage.toFixed(1)}% Kontextfenster verfügbar
            </p>
            {contextPercentage > 90 && (
              <p className="text-xs text-destructive mt-1">
                Warnung: Die Dateigröße könnte die Analysekapazität überschreiten.
              </p>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="w-16 h-16 rounded-full bg-secondary flex items-center justify-center">
            <Upload className="h-8 w-8 text-muted-foreground" />
          </div>
          <div className="text-center">
            <p className="font-medium">Dateien hierher ziehen oder</p>
            <label htmlFor="file-upload" className="cursor-pointer text-primary hover:underline">
              klicken zum Auswählen
            </label>
            <p className="text-sm text-muted-foreground mt-1">
              Unterstützte Formate: PDF, DOC, DOCX, TXT
            </p>
          </div>
          <input
            id="file-upload"
            type="file"
            accept=".pdf,.doc,.docx,.txt"
            onChange={handleFileChange}
            className="hidden"
            multiple // Erlaube Mehrfachauswahl
          />
        </>
      )}
    </div>
  );
  
  const renderProcessingView = () => (
    <div className="p-8 flex flex-col items-center gap-4 animate-fade-in">
      <div className="w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-600 dark:text-blue-400 animate-spin" />
      </div>
      <div className="text-center">
        <p className="font-medium text-lg">Deine Datei wird verarbeitet</p>
        <p className="text-muted-foreground mt-1">
          Unsere KI analysiert deinen Text und erstellt Lernmaterialien...
        </p>
      </div>
      <div className="w-full max-w-md">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-muted-foreground">Fortschritt:</span>
          <span className="font-medium">{processingProgress.toFixed(0)}%</span>
        </div>
        <Progress value={processingProgress} className="h-2" />
      </div>
      <p className="text-sm text-muted-foreground mt-2">
        Dies kann je nach Dateigröße einige Minuten dauern.
      </p>
    </div>
  );
  
  const renderResultsView = () => {
    if (!results || !results.data) {
      return (
        <div className="text-center py-8">
          <p>Keine Ergebnisse verfügbar</p>
          <Button 
            variant="outline" 
            className="mt-4"
            onClick={resetUpload}
          >
            Zurück zum Upload
          </Button>
        </div>
      );
    }

    const { flashcards, test_questions, topics } = results.data;
    
    return (
      <Tabs defaultValue="flashcards" className="mt-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="flashcards">Karteikarten ({flashcards.length})</TabsTrigger>
          <TabsTrigger value="topics">Themen ({topics.subtopics.length + 1})</TabsTrigger>
          <TabsTrigger value="questions">Testfragen ({test_questions.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="flashcards">
          <FlashcardView flashcards={flashcards} />
        </TabsContent>
        <TabsContent value="topics">
          <TopicsView topics={topics} />
        </TabsContent>
        <TabsContent value="questions">
          <QuestionsView questions={test_questions} />
        </TabsContent>
      </Tabs>
    );
  };
  
  return (
    <section id="upload" className="section-container">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12 space-y-4">
          <h2 className="text-3xl md:text-4xl font-bold animate-fade-in">
            Lade deine Dokumente hoch
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto animate-fade-in">
            Stelle uns deine Unterlagen zur Verfügung, und unsere KI wird daraus optimales Lernmaterial erstellen.
          </p>
        </div>
        
        <Card className="border border-border/50 shadow-soft overflow-hidden animate-slide-up">
          <CardHeader className="pb-4">
            <CardTitle>Dokument hochladen</CardTitle>
            <CardDescription>
              Unterstützte Formate: PDF, DOC, DOCX, TXT
            </CardDescription>
          </CardHeader>
          
          <CardContent>
            {activeView === 'upload' && renderUploadView()}
            {activeView === 'processing' && renderProcessingView()}
            {activeView === 'results' && renderResultsView()}
          </CardContent>
          
          <CardFooter className="flex justify-end border-t bg-secondary/50 pt-4">
            {activeView === 'upload' ? (
              <>
                {files && files.length > 0 && (
                  <Button 
                    variant="outline" 
                    className="mr-3"
                    onClick={resetUpload}
                  >
                    Abbrechen
                  </Button>
                )}
                <Button 
                  onClick={handleUpload} 
                  disabled={!files || files.length === 0 || isUploading || contextPercentage > 100}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird hochgeladen...
                    </>
                  ) : (
                    'Hochladen' // Oder 'Dateien hochladen'?
                  )}
                </Button>
              </>
            ) : activeView === 'processing' ? (
              <Button 
                variant="outline" 
                onClick={fetchResults}
                className="w-full"
              >
                <RotateCw className="mr-2 h-4 w-4" />
                Status aktualisieren
              </Button>
            ) : (
              <Button 
                variant="outline"
                onClick={resetUpload}
              >
                Weitere Datei hochladen
              </Button>
            )}
          </CardFooter>
        </Card>
      </div>
    </section>
  );
};

export default ExamUploader;
