import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { X, Clock, RefreshCw, FileText, Layers } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';

// Typen für die Sessions
type Session = {
  upload_id: string;
  session_id: string;
  main_topic: string;
  created_at: string;
  last_used_at: string;
};

interface HistorySidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSession: (session: Session) => void;
}

const HistorySidebar = ({ isOpen, onClose, onSelectSession }: HistorySidebarProps) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();
  const { toast } = useToast();

  // Sessions laden
  const loadSessions = useCallback(async () => {
    if (!user?.id) return;
    
    setLoading(true);
    setError(null);
    
    try {
      console.log('🔄 Lade Sessions für Benutzer:', user.id);
      const response = await axios.get(
        `${import.meta.env.VITE_API_URL}/api/uploads/sessions/${user.id}?t=${Date.now()}`,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('token')}`,
          },
        }
      );
      
      if (response.data && Array.isArray(response.data)) {
        console.log(`✅ ${response.data.length} Sessions geladen`);
        setSessions(response.data);
      } else {
        console.error('❌ Unerwartetes Datenformat:', response.data);
        setError('Keine Sessions gefunden oder unerwartetes Datenformat');
      }
    } catch (err) {
      console.error('❌ Fehler beim Laden der Sessions:', err);
      setError('Fehler beim Laden der Sessions');
      toast({
        title: 'Fehler',
        description: 'Sessions konnten nicht geladen werden',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [user, toast]);

  // Sessions beim Öffnen der Sidebar laden
  useEffect(() => {
    if (isOpen) {
      loadSessions();
    }
  }, [isOpen, loadSessions]);

  // Formatieren eines Datums
  const formatDate = (dateString: string) => {
    try {
      return format(new Date(dateString), 'dd. MMM, HH:mm', { locale: de });
    } catch {
      return 'Unbekanntes Datum';
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed right-0 top-0 z-50 h-full w-80 bg-white shadow-lg dark:bg-gray-900"
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        >
          <div className="flex h-full flex-col">
            {/* Header */}
            <div className="flex items-center justify-between border-b p-4 dark:border-gray-700">
              <h2 className="text-lg font-semibold">Verlauf</h2>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-5 w-5" />
              </Button>
            </div>

            {/* Refresh Button */}
            <div className="border-b p-2 dark:border-gray-700">
              <Button 
                variant="outline" 
                className="w-full" 
                onClick={loadSessions}
                disabled={loading}
              >
                <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
                {loading ? 'Lade...' : 'Aktualisieren'}
              </Button>
            </div>

            {/* Sessions List */}
            <ScrollArea className="flex-1">
              <div className="p-3">
                {loading ? (
                  // Lade-Skeletons
                  Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="mb-3">
                      <Skeleton className="h-20 w-full rounded-md" />
                    </div>
                  ))
                ) : error ? (
                  // Fehleranzeige
                  <div className="flex flex-col items-center justify-center p-4 text-center text-gray-500">
                    <p>{error}</p>
                    <Button 
                      variant="link" 
                      onClick={loadSessions} 
                      className="mt-2"
                    >
                      Erneut versuchen
                    </Button>
                  </div>
                ) : sessions.length === 0 ? (
                  // Keine Sessions vorhanden
                  <div className="flex flex-col items-center justify-center p-4 text-center text-gray-500">
                    <p>Keine Sessions gefunden</p>
                  </div>
                ) : (
                  // Sessions anzeigen
                  sessions.map((session) => (
                    <Card
                      key={session.upload_id}
                      className="mb-3 cursor-pointer p-3 transition-all hover:bg-gray-100 dark:hover:bg-gray-800"
                      onClick={() => onSelectSession(session)}
                    >
                      <div className="flex flex-col">
                        <div className="font-medium line-clamp-2">{session.main_topic}</div>
                        <div className="mt-2 flex items-center text-xs text-gray-500">
                          <Clock className="mr-1 h-3 w-3" />
                          {formatDate(session.last_used_at || session.created_at)}
                        </div>
                        <div className="mt-1 flex items-center text-xs text-gray-500">
                          <Layers className="mr-1 h-3 w-3" />
                          <span>Session ID: {session.session_id.substring(0, 8)}...</span>
                        </div>
                      </div>
                    </Card>
                  ))
                )}
              </div>
            </ScrollArea>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default HistorySidebar; 