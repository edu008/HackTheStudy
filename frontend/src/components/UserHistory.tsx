import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { UploadCloud, Lightbulb, BookOpen, Network, CreditCard, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useToast } from '@/hooks/use-toast';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

interface UserHistoryProps {
  onSessionSelect?: (sessionId: string, activityType: string, mainTopic: string) => void;
}

const UserHistory = ({ onSessionSelect }: UserHistoryProps) => {
  const { user, fetchActivities } = useAuth();
  const [activities, setActivities] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedActivity, setSelectedActivity] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState<string | null>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    if (user) {
      loadActivities();
    }
  }, [user]);

  const loadActivities = async () => {
    setIsLoading(true);
    try {
      const response = await axios.get(`${API_URL}/api/v1/user-history`, { withCredentials: true });

      if (response.data.success && Array.isArray(response.data.activities)) {
        setActivities(response.data.activities);
        console.log("🔍 Geladene Aktivitäten:", response.data.activities);
      } else {
        console.warn("⚠️ Keine Aktivitäten gefunden.");
        setActivities([]);
      }
    } catch (error) {
      console.error("❌ Fehler beim Abrufen der Aktivitäten:", error);
      toast({
        title: "Fehler",
        description: "Die Aktivitäten konnten nicht geladen werden.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString();
  };

  const getActivityIcon = (type: string) => {
    const icons: Record<string, JSX.Element> = {
      upload: <UploadCloud className="h-5 w-5 text-blue-500" />,
      flashcard: <Lightbulb className="h-5 w-5 text-yellow-500" />,
      test: <BookOpen className="h-5 w-5 text-green-500" />,
      concept: <Network className="h-5 w-5 text-purple-500" />,
      payment: <CreditCard className="h-5 w-5 text-emerald-500" />,
      account: <User className="h-5 w-5 text-indigo-500" />,
    };
    return icons[type] || <UploadCloud className="h-5 w-5 text-gray-500" />;
  };

  const handleActivityClick = async (activity: any) => {
    if (!['upload', 'flashcard', 'test', 'concept'].includes(activity.type)) {
      return;
    }

    setSelectedActivity(activity.id);
    let sessionId = activity.details?.session_id;

    if (!sessionId) {
      console.warn("⚠️ Keine `session_id` in der Aktivität. Versuche, sie zu finden...");
      const uploadActivity = activities.find(a => a.type === 'upload' && a.details?.main_topic === activity.details?.main_topic);
      sessionId = uploadActivity?.details?.session_id;
    }

    if (!sessionId) {
      toast({
        title: "Fehler",
        description: "Keine Session-ID gefunden.",
        variant: "destructive",
      });
      return;
    }

    loadSessionData(sessionId, activity.type, activity.details?.main_topic || "Unbekanntes Thema");
  };

  const loadSessionData = async (sessionId: string, activityType: string, mainTopic: string) => {
    setLoadingSession(sessionId);

    try {
      const response = await axios.get(`${API_URL}/api/v1/results/${sessionId}`, {
        withCredentials: true,
      });

      if (response.data.success) {
        console.log(`✅ Session "${mainTopic}" geladen:`, response.data);
        if (onSessionSelect) {
          onSessionSelect(sessionId, activityType, mainTopic);
          toast({
            title: "Analyse geladen",
            description: `Die Analyse "${mainTopic}" wurde erfolgreich geladen.`,
          });
        } else {
          navigate(`/?session=${sessionId}#${activityType === 'concept' ? 'concept-mapper' : activityType === 'test' ? 'test-simulator' : 'flashcards'}`);
        }
      } else {
        throw new Error("Keine Daten gefunden");
      }
    } catch (error) {
      console.error("❌ Fehler beim Laden der Session:", error);
      toast({
        title: "Fehler beim Laden",
        description: "Die Daten für diese Aktivität konnten nicht geladen werden.",
        variant: "destructive",
      });
    } finally {
      setLoadingSession(null);
    }
  };

  return (
    <div className="py-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">Aktivitätshistorie</h3>
        <Button variant="outline" size="sm" onClick={loadActivities} disabled={isLoading}>
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-6 pr-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-5 w-5 rounded-full" />
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-24" />
              <Separator />
            </div>
          ))}
        </div>
      ) : activities.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">Keine Aktivitäten gefunden.</div>
      ) : (
        <ScrollArea className="h-[400px]">
          <div className="space-y-6 pr-4">
            {activities.map((activity) => (
              <div key={activity.id} className="space-y-2">
                <div
                  className={`flex items-center justify-between p-2 rounded-md transition-colors ${
                    ['upload', 'flashcard', 'test', 'concept'].includes(activity.type)
                      ? 'cursor-pointer ' + (selectedActivity === activity.id ? 'bg-secondary' : 'hover:bg-secondary/50')
                      : ''
                  }`}
                  onClick={() => handleActivityClick(activity)}
                >
                  <div className="flex items-center space-x-3">
                    {getActivityIcon(activity.type)}
                    <div>
                      <h4 className="text-sm font-medium">{activity.title}</h4>
                      <p className="text-xs text-muted-foreground">{formatDate(activity.timestamp)}</p>
                    </div>
                  </div>
                  {loadingSession === activity.details?.session_id && <Skeleton className="h-5 w-5 rounded-full animate-pulse" />}
                </div>
                <Separator />
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
};

export default UserHistory;
