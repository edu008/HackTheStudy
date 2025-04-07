import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import ExamUploader from "@/components/ExamUploader";
import FlashcardGenerator from "@/components/FlashcardGenerator";
import TestSimulator from "@/components/TestSimulator";
import ConceptMapper from "@/components/ConceptMapper";
import { useToast } from "@/components/ui/use-toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from "@/components/ui/progress";
import { RotateCw } from 'lucide-react';
import * as uploadService from "@/lib/api/uploadService";
import { Flashcard, Question, Topic, UploadResults } from "@/types";

const TaskPage = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  // State für Anwendungsdaten
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [results, setResults] = useState<UploadResults | null>(null);
  const [activeTab, setActiveTab] = useState('upload');
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);

  // Überprüfe, ob der Benutzer angemeldet ist
  useEffect(() => {
    if (!isLoading && !user) {
      navigate('/'); // Zurück zur Startseite, wenn nicht angemeldet
    }
  }, [user, isLoading, navigate]);

  // Lade letzte Session, wenn Benutzer eingeloggt ist
  useEffect(() => {
    if (user) {
      // Lade die letzte Session, falls vorhanden
      const lastSessionId = localStorage.getItem("current_session_id");
      if (lastSessionId) {
        setSessionId(lastSessionId);
        // Hier könnten Daten für die letzte Session geladen werden
        fetchResults(lastSessionId);
      }
    }
  }, [user]);

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
            fetchResults(sessionId);
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

  const handleUploadComplete = (uploadSessionId: string) => {
    setSessionId(uploadSessionId);
    setIsProcessing(true);
    setProcessingProgress(0);
    setActiveTab('processing');
    
    // Speichere die aktuelle Session-ID lokal
    localStorage.setItem("current_session_id", uploadSessionId);
  };

  const fetchResults = async (sid: string) => {
    try {
      const data = await uploadService.getUploadResults(sid);
      setResults(data);
      setActiveTab('results');
      
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
  };

  const resetSession = () => {
    setSessionId(null);
    setIsProcessing(false);
    setProcessingProgress(0);
    setResults(null);
    setActiveTab('upload');
    localStorage.removeItem("current_session_id");
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center">
        <div className="animate-pulse text-lg">Wird geladen...</div>
      </div>
    );
  }

  if (!user) {
    return null; // Redirect erfolgt im useEffect
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1">
        <div className="container mx-auto py-8">
          <div className="mb-8 text-center">
            <h1 className="text-4xl font-bold mb-4">Lernmaterialien generieren</h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Lade deine Unterlagen oder Texte hoch und lass automatisch Karteikarten, Testfragen und eine Themenanalyse erstellen.
            </p>
          </div>
          
          <Tabs value={activeTab} onValueChange={setActiveTab} className="max-w-4xl mx-auto">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="upload" disabled={isProcessing}>Hochladen</TabsTrigger>
              <TabsTrigger value="processing" disabled={!isProcessing}>Verarbeitung</TabsTrigger>
              <TabsTrigger value="results" disabled={!results}>Ergebnisse</TabsTrigger>
            </TabsList>
            
            <TabsContent value="upload">
              <ExamUploader onUploadComplete={handleUploadComplete} />
            </TabsContent>
            
            <TabsContent value="processing">
              <Card>
                <CardHeader>
                  <CardTitle>Dokument wird verarbeitet</CardTitle>
                  <CardDescription>
                    Deine Datei wird analysiert und Lernmaterialien werden generiert
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="flex justify-center">
                    <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-primary"></div>
                  </div>
                  
                  <div className="w-full max-w-md mx-auto">
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-muted-foreground">Fortschritt:</span>
                      <span className="font-medium">{processingProgress.toFixed(0)}%</span>
                    </div>
                    <Progress value={processingProgress} className="h-2" />
                  </div>
                  
                  <div className="text-center space-y-2">
                    <p className="text-sm text-muted-foreground">
                      Dies kann einige Minuten dauern, abhängig von der Dateigröße und Komplexität.
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Bitte schließe diese Seite nicht, während dein Dokument verarbeitet wird.
                    </p>
                  </div>
                </CardContent>
                <CardFooter className="flex justify-center">
                  <Button 
                    variant="outline" 
                    onClick={() => sessionId && fetchResults(sessionId)}
                    className="w-52"
                  >
                    <RotateCw className="mr-2 h-4 w-4" />
                    Status aktualisieren
                  </Button>
                </CardFooter>
              </Card>
            </TabsContent>
            
            <TabsContent value="results">
              {results && results.data ? (
                <div>
                  <Tabs defaultValue="flashcards">
                    <TabsList className="grid w-full grid-cols-3">
                      <TabsTrigger value="flashcards">Karteikarten</TabsTrigger>
                      <TabsTrigger value="concepts">Themenübersicht</TabsTrigger>
                      <TabsTrigger value="questions">Testfragen</TabsTrigger>
                    </TabsList>
                    
                    <TabsContent value="flashcards">
                      <FlashcardGenerator initialFlashcards={results.data.flashcards} />
                    </TabsContent>
                    
                    <TabsContent value="concepts">
                      <ConceptMapper 
                        mainTopic={results.data.topics.main_topic} 
                        subtopics={results.data.topics.subtopics}
                        connections={results.data.connections}
                      />
                    </TabsContent>
                    
                    <TabsContent value="questions">
                      <TestSimulator questions={results.data.test_questions} />
                    </TabsContent>
                  </Tabs>
                  
                  <div className="mt-8 flex justify-center">
                    <Button 
                      variant="outline"
                      onClick={resetSession}
                    >
                      Weitere Datei hochladen
                    </Button>
                  </div>
                </div>
              ) : (
                <Card>
                  <CardContent className="py-8 text-center">
                    <p>Keine Ergebnisse verfügbar</p>
                    <Button 
                      variant="outline" 
                      className="mt-4"
                      onClick={resetSession}
                    >
                      Zurück zum Upload
                    </Button>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default TaskPage; 