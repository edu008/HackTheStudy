import { useState } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FileText, Upload, CheckCircle, Loader2, X, AlertCircle } from 'lucide-react';
import { useToast } from "@/hooks/use-toast";
import { useMutation } from '@tanstack/react-query';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// This interface matches the response from the backend's upload endpoint
interface BackendUploadResponse {
  success: boolean;
  message: string;
  session_id: string;
  task_id: string;
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

interface ExamUploaderProps {
  onUploadSuccess?: (data: UploadResponse) => void;
}

const ExamUploader = ({ onUploadSuccess }: ExamUploaderProps) => {
  const { toast } = useToast();
  const [files, setFiles] = useState<File[]>([]);
  const [isUploaded, setIsUploaded] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: async (filesToUpload: File[]) => {
      console.log('DEBUG: Starting file upload to backend');
      console.log(`DEBUG: API URL: ${API_URL}`);
      console.log(`DEBUG: Uploading ${filesToUpload.length} files:`, filesToUpload.map(f => f.name));
      
      // Get the token from localStorage
      const token = localStorage.getItem('exammaster_token');
      
      const formData = new FormData();
      filesToUpload.forEach(file => {
        console.log(`DEBUG: Appending file to FormData: ${file.name} (${file.size} bytes, type: ${file.type})`);
        formData.append('file', file); // Änderung von 'files[]' zu 'file'
      });
      
      console.log('DEBUG: Sending POST request to backend');
      const response = await axios.post<BackendUploadResponse>(`${API_URL}/api/v1/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          'Authorization': token ? `Bearer ${token}` : '',
        },
        withCredentials: true,
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            console.log(`DEBUG: Upload progress: ${progress}%`);
            setUploadProgress(progress);
          }
        },
      });

      console.log('DEBUG: Received response from backend:', response.data);
      
      // Wait for the backend to process the upload
      
      // Poll the results endpoint until the data is available
      let retries = 0;
      const maxRetries = 30; // Maximum number of retries (30 * 2 seconds = 60 seconds)
      const retryInterval = 2000; // 2 seconds
      
      while (retries < maxRetries) {
        try {
          const resultsResponse = await axios.get<{ success: boolean, data: SessionData }>(
            `${API_URL}/api/v1/results/${response.data.session_id}`,
            { 
              headers: {
                'Authorization': token ? `Bearer ${token}` : '',
              },
              withCredentials: true 
            }
          );
          
          if (resultsResponse.data.success && resultsResponse.data.data) {
            
            // Combine the upload response and results data
            const completeResponse: UploadResponse = {
              success: true,
              message: response.data.message,
              session_id: response.data.session_id,
              flashcards: resultsResponse.data.data.flashcards || [],
              questions: resultsResponse.data.data.test_questions || []
            };
            
            return completeResponse;
          }
        } catch (error) {
        }
        
        // Wait before retrying
        await new Promise(resolve => setTimeout(resolve, retryInterval));
        retries++;
      }
      
      // If we've exhausted all retries, return a partial response with an error message
      return {
        success: true,
        message: "Upload successful, but processing is taking longer than expected. The server might be busy or the worker might not be running. Please try again later or contact support.",
        session_id: response.data.session_id,
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    
    if (selectedFiles.length > 0) {
      if (files.length + selectedFiles.length > 5) {
        toast({
          title: "Zu viele Dateien",
          description: "Maximal 5 Dateien können gleichzeitig hochgeladen werden.",
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
      
      setFiles(prevFiles => [...prevFiles, ...selectedFiles]);
    }
  };

  const handleUpload = () => {
    if (files.length === 0) return;
    
    console.log('DEBUG: handleUpload called with files:', files);
    setError(null);
    setUploadProgress(0);
    uploadMutation.mutate(files);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    
    const droppedFiles = Array.from(e.dataTransfer.files);
    
    if (files.length + droppedFiles.length > 5) {
      toast({
        title: "Zu viele Dateien",
        description: "Maximal 5 Dateien können gleichzeitig hochgeladen werden.",
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
    
    setFiles(prevFiles => [...prevFiles, ...droppedFiles]);
  };

  const removeFile = (index: number) => {
    setFiles(prevFiles => prevFiles.filter((_, i) => i !== index));
  };

  const resetUpload = () => {
    setFiles([]);
    setIsUploaded(false);
    setError(null);
  };
  
  return (
    <section id="upload" className="section-container">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12 space-y-4">
          <h2 className="text-3xl md:text-4xl font-bold animate-fade-in">
            Lade deine Prüfungen hoch
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto animate-fade-in">
            Stelle uns deine alten Moodle-Prüfungen zur Verfügung, und unsere KI wird daraus optimales Lernmaterial erstellen.
          </p>
        </div>
        
        <Card className="border border-border/50 shadow-soft overflow-hidden animate-slide-up relative">
          <CardHeader className="pb-4">
            <CardTitle>Prüfungen hochladen</CardTitle>
            <CardDescription>
              Unterstützte Formate: PDF, TXT (max. 5 Dateien)
            </CardDescription>
          </CardHeader>
          
          <CardContent>
            {!isUploaded ? (
              <>
                <div 
                  className={`p-8 border-2 border-dashed rounded-lg flex flex-col items-center justify-center gap-4 transition-all ${
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
                          <p className="font-medium">{files.length} Datei{files.length > 1 ? 'en' : ''} ausgewählt</p>
                        </div>
                      </div>
                      
                      <div className="space-y-2 max-h-48 overflow-y-auto p-2">
                        {files.map((file, index) => (
                          <div 
                            key={index} 
                            className="flex items-center justify-between p-3 bg-secondary/30 rounded-lg animate-fade-in"
                            style={{ animationDelay: `${index * 100}ms` }}
                          >
                            <div className="flex items-center space-x-3">
                              <FileText className="h-5 w-5 text-primary" />
                              <div>
                                <p className="text-sm font-medium truncate max-w-[200px]">{file.name}</p>
                                <p className="text-xs text-muted-foreground">
                                  {(file.size / 1024 / 1024).toFixed(2)} MB
                                </p>
                              </div>
                            </div>
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-8 w-8"
                              onClick={() => removeFile(index)}
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        ))}
                      </div>
                      
                      {files.length < 5 && (
                        <div className="mt-4 text-center">
                          <Button 
                            variant="outline" 
                            size="sm" 
                            className="text-xs"
                            onClick={() => document.getElementById('file-upload')?.click()}
                          >
                            Weitere Dateien hinzufügen
                          </Button>
                          <input
                            id="file-upload"
                            type="file"
                            accept=".pdf,.txt"
                            onChange={handleFileChange}
                            className="hidden"
                            multiple
                          />
                        </div>
                      )}
                    </div>
                  ) : (
                    <>
                      <div className="w-16 h-16 rounded-full bg-secondary flex items-center justify-center">
                        <Upload className="h-8 w-8 text-muted-foreground" />
                      </div>
                      <div className="text-center">
                        <p className="font-medium">Dateien hierher ziehen oder klicken zum Auswählen</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          Unterstützte Formate: PDF, TXT (max. 5 Dateien, je max. 10MB)
                        </p>
                      </div>
                      <input
                        id="file-upload"
                        type="file"
                        accept=".pdf,.txt"
                        onChange={handleFileChange}
                        className="absolute top-0 left-0 w-full h-full opacity-0 cursor-pointer"
                        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 1 }}
                        multiple
                      />
                    </>
                  )}
                </div>
                
                {error && (
                  <div className="mt-4 p-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-3">
                    <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="font-medium text-red-700 dark:text-red-400">Fehler beim Hochladen</p>
                      <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="p-8 flex flex-col items-center gap-4 animate-fade-in">
                <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                  <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
                </div>
                <div className="text-center">
                  <p className="font-medium text-lg">Erfolgreich hochgeladen!</p>
                  <p className="text-muted-foreground mt-1">
                    {uploadMutation.data && uploadMutation.data.flashcards.length === 0 && uploadMutation.data.questions.length === 0 ? (
                      uploadMutation.data.message || "Die Dateien wurden hochgeladen, aber es konnten keine Lernmaterialien erstellt werden. Bitte versuche es später erneut."
                    ) : (
                      "Die KI hat deine Prüfungen analysiert und Lernmaterialien erstellt."
                    )}
                  </p>
                </div>
              </div>
            )}
          </CardContent>
          
          <CardFooter className="flex justify-end border-t bg-secondary/50 pt-4">
            {!isUploaded ? (
              <>
                {files.length > 0 && (
                  <Button 
                    variant="outline" 
                    className="mr-3"
                    onClick={resetUpload}
                  >
                    Zurücksetzen
                  </Button>
                )}
                <Button 
                  onClick={handleUpload} 
                  disabled={files.length === 0 || uploadMutation.isPending}
                >
                  {uploadMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {uploadProgress > 0 ? `${uploadProgress}%` : 'Wird hochgeladen...'}
                    </>
                  ) : (
                    'Hochladen und Analysieren'
                  )}
                </Button>
              </>
            ) : (
              <Button 
                variant="outline"
                onClick={resetUpload}
              >
                Weitere Prüfungen hochladen
              </Button>
            )}
          </CardFooter>
        </Card>
      </div>
    </section>
  );
};

export default ExamUploader;
