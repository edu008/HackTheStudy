import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import FileUpload from '@/components/FileUpload';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Upload, Topic } from '@/types';
import * as uploadService from '@/lib/api/uploadService';
import { File as FileIcon, Trash2 } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

const UploadPage = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<string>('');
  const [isLoadingUploads, setIsLoadingUploads] = useState(false);
  const [activeTab, setActiveTab] = useState('upload');

  // Umleitung, wenn nicht angemeldet
  useEffect(() => {
    if (!isLoading && !user) {
      navigate('/signin');
    }
  }, [user, isLoading, navigate]);

  // Lade Uploads des Benutzers
  useEffect(() => {
    const fetchUploads = async () => {
      if (user) {
        setIsLoadingUploads(true);
        try {
          const userUploads = await uploadService.getUserUploads();
          setUploads(userUploads);
        } catch (error) {
          console.error('Fehler beim Laden der Uploads:', error);
        } finally {
          setIsLoadingUploads(false);
        }
      }
    };

    if (activeTab === 'manage') {
      fetchUploads();
    }
  }, [user, activeTab]);

  // Lade Themen (Mock-Daten)
  useEffect(() => {
    // In einer realen Anwendung würden diese Daten vom Backend kommen
    setTopics([
      { id: '1', name: 'Mathematik' },
      { id: '2', name: 'Informatik' },
      { id: '3', name: 'Physik' },
      { id: '4', name: 'Biologie' }
    ]);
  }, []);

  // Upload abgeschlossen
  const handleUploadComplete = (newUploads: Upload[]) => {
    setUploads(prev => [...newUploads, ...prev]);
    setActiveTab('manage');
  };

  // Upload löschen
  const handleDeleteUpload = async (id: string) => {
    try {
      await uploadService.deleteUpload(id);
      setUploads(prev => prev.filter(upload => upload.id !== id));
    } catch (error) {
      console.error('Fehler beim Löschen des Uploads:', error);
    }
  };

  // Formatiere Dateigröße
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Formatiere Datum
  const formatDate = (dateString: string): string => {
    try {
      return format(new Date(dateString), 'dd. MMMM yyyy, HH:mm', { locale: de });
    } catch (e) {
      return dateString;
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center">
        <div className="animate-pulse text-lg">Wird geladen...</div>
      </div>
    );
  }

  if (!user) {
    return null; // Umleitung erfolgt in useEffect
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Dokumentenverwaltung</h1>
          <p className="text-gray-500 mt-2">
            Lade Dokumente hoch und verwalte deine bestehenden Uploads
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="upload">Neue Dokumente</TabsTrigger>
            <TabsTrigger value="manage">Meine Dokumente</TabsTrigger>
          </TabsList>
          
          <TabsContent value="upload" className="space-y-6">
            <div className="flex items-center mb-4">
              <div className="w-64">
                <label className="text-sm font-medium mb-1 block">Thema auswählen (optional)</label>
                <Select value={selectedTopic} onValueChange={setSelectedTopic}>
                  <SelectTrigger>
                    <SelectValue placeholder="Thema auswählen" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Kein Thema</SelectItem>
                    {topics.map((topic) => (
                      <SelectItem key={topic.id} value={topic.id}>
                        {topic.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            <FileUpload 
              onUploadComplete={handleUploadComplete}
              topicId={selectedTopic || undefined}
            />
          </TabsContent>
          
          <TabsContent value="manage">
            {isLoadingUploads ? (
              <div className="py-12 text-center">
                <div className="animate-pulse text-lg">Dokumente werden geladen...</div>
              </div>
            ) : uploads.length === 0 ? (
              <Card className="border-dashed">
                <CardContent className="py-12 text-center">
                  <FileIcon className="h-12 w-12 mx-auto mb-4 text-gray-400" />
                  <h3 className="text-lg font-medium mb-2">Keine Dokumente gefunden</h3>
                  <p className="text-gray-500 mb-4">
                    Du hast noch keine Dokumente hochgeladen.
                  </p>
                  <Button onClick={() => setActiveTab('upload')}>
                    Dokument hochladen
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-6">
                {uploads.map((upload) => (
                  <Card key={upload.id}>
                    <CardHeader className="pb-2">
                      <div className="flex justify-between items-start">
                        <div>
                          <CardTitle className="text-lg">{upload.original_filename}</CardTitle>
                          <CardDescription>
                            {upload.created_at && formatDate(upload.created_at)}
                          </CardDescription>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDeleteUpload(upload.id)}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center justify-between text-sm">
                        <div>
                          <span className="font-medium">Dateityp:</span>{' '}
                          <span className="text-gray-600">{upload.file_type}</span>
                        </div>
                        <div>
                          <span className="font-medium">Größe:</span>{' '}
                          <span className="text-gray-600">{formatFileSize(upload.file_size)}</span>
                        </div>
                        <div>
                          <span className="font-medium">Thema:</span>{' '}
                          <span className="text-gray-600">
                            {upload.topic_id 
                              ? topics.find(t => t.id === upload.topic_id)?.name || 'Unbekannt'
                              : 'Kein Thema'}
                          </span>
                        </div>
                        <Button size="sm" variant="outline">
                          Anzeigen
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </main>
      <Footer />
    </div>
  );
};

export default UploadPage; 