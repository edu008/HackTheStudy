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
  const { user, activities, fetchActivities } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [selectedActivity, setSelectedActivity] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState<string | null>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    const loadActivities = async () => {
      if (user) {
        setIsLoading(true);
        try {
          await fetchActivities();
        } catch (error) {
          console.error("Error fetching activities:", error);
        } finally {
          setIsLoading(false);
        }
      }
    };
    
    loadActivities();
  }, [user, fetchActivities]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffInMs = now.getTime() - date.getTime();
    const diffInHours = diffInMs / (1000 * 60 * 60);
    
    if (diffInHours < 24) {
      return `${Math.floor(diffInHours)} hours ago`;
    } else {
      const diffInDays = diffInHours / 24;
      if (diffInDays < 30) {
        return `${Math.floor(diffInDays)} days ago`;
      } else {
        return date.toLocaleDateString();
      }
    }
  };

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'upload':
        return <UploadCloud className="h-5 w-5 text-blue-500" />;
      case 'flashcard':
        return <Lightbulb className="h-5 w-5 text-yellow-500" />;
      case 'test':
        return <BookOpen className="h-5 w-5 text-green-500" />;
      case 'concept':
        return <Network className="h-5 w-5 text-purple-500" />;
      case 'payment':
        return <CreditCard className="h-5 w-5 text-emerald-500" />;
      case 'account':
        return <User className="h-5 w-5 text-indigo-500" />;
      default:
        return <UploadCloud className="h-5 w-5 text-blue-500" />;
    }
  };

  const handleRefresh = async () => {
    setIsLoading(true);
    await fetchActivities();
    setIsLoading(false);
  };

  const handleActivityClick = async (activity: any) => {
    // Only process upload, flashcard, test, and concept activities
    if (!['upload', 'flashcard', 'test', 'concept'].includes(activity.type)) {
      return;
    }

    setSelectedActivity(activity.id);

    // Check if we have a session ID in the activity details
    if (!activity.details || !activity.details.session_id) {
      // Try to find the session ID from the upload activity if this is a derived activity
      if (activity.details && activity.details.main_topic) {
        const mainTopic = activity.details.main_topic;
        const uploadActivity = activities.find(
          a => a.type === 'upload' && 
               a.details && 
               a.details.main_topic === mainTopic
        );
        
        if (uploadActivity && uploadActivity.details && uploadActivity.details.session_id) {
          loadSessionData(
            uploadActivity.details.session_id, 
            activity.type, 
            mainTopic
          );
          return;
        }
      }
      
      toast({
        title: "Keine Session-ID gefunden",
        description: "Die Aktivität konnte nicht geladen werden, da keine Session-ID gefunden wurde.",
        variant: "destructive",
      });
      return;
    }

    const sessionId = activity.details.session_id;
    const mainTopic = activity.details.main_topic || "Unbekanntes Thema";
    
    loadSessionData(sessionId, activity.type, mainTopic);
  };

  const loadSessionData = async (sessionId: string, activityType: string, mainTopic: string) => {
    setLoadingSession(sessionId);
    
    try {
      // Check if the session data exists
      const response = await axios.get(`${API_URL}/api/v1/results/${sessionId}`, {
        withCredentials: true
      });
      
      if (response.data.success) {
        // If we have a callback, call it with the session ID and activity type
        if (onSessionSelect) {
          onSessionSelect(sessionId, activityType, mainTopic);
          
          toast({
            title: "Analyse geladen",
            description: `Die Analyse "${mainTopic}" wurde erfolgreich geladen.`,
          });
        } else {
          // If no callback, navigate to the home page with the session ID
          navigate(`/?session=${sessionId}#${activityType === 'concept' ? 'concept-mapper' : 
                                            activityType === 'test' ? 'test-simulator' : 
                                            'flashcards'}`);
        }
      } else {
        throw new Error("Keine Daten für diese Session gefunden");
      }
    } catch (error) {
      console.error("Error loading session data:", error);
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
        <h3 className="text-lg font-medium">Activity History</h3>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={handleRefresh}
          disabled={isLoading}
        >
          Refresh
        </Button>
      </div>
      
      {!user ? (
        <div className="text-center py-10 text-muted-foreground">
          Please sign in to view your history
        </div>
      ) : isLoading ? (
        <div className="space-y-6 pr-4">
          {Array(5).fill(0).map((_, i) => (
            <div key={i} className="space-y-2">
              <div className="flex items-center space-x-3">
                <Skeleton className="h-5 w-5 rounded-full" />
                <div className="space-y-1">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-24" />
                </div>
              </div>
              <Separator />
            </div>
          ))}
        </div>
      ) : activities.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          No activity history available yet
        </div>
      ) : (
        <ScrollArea className="h-[400px]">
          <div className="space-y-6 pr-4">
            {activities.map((activity) => (
              <div key={activity.id} className="space-y-2">
                <div className="space-y-2">
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
                        <p className="text-xs text-muted-foreground">
                          {formatDate(activity.timestamp)}
                        </p>
                      </div>
                    </div>
                    
                    {loadingSession === activity.details?.session_id && (
                      <Skeleton className="h-5 w-5 rounded-full animate-pulse" />
                    )}
                  </div>
                  
                  {/* Show details for activities */}
                  {activity.details && (
                    <div className="ml-8 text-xs">
                      {/* Upload activity details */}
                      {activity.type === 'upload' && (
                        <>
                          {activity.details.main_topic && (
                            <p><span className="font-medium">Topic:</span> {activity.details.main_topic}</p>
                          )}
                          {activity.details.subtopics && activity.details.subtopics.length > 0 && (
                            <p><span className="font-medium">Subtopics:</span> {activity.details.subtopics.slice(0, 3).join(', ')}{activity.details.subtopics.length > 3 ? '...' : ''}</p>
                          )}
                          {activity.details.files && activity.details.files.length > 0 && (
                            <p><span className="font-medium">Files:</span> {activity.details.files.slice(0, 2).join(', ')}{activity.details.files.length > 2 ? '...' : ''}</p>
                          )}
                        </>
                      )}
                      
                      {/* Flashcard activity details */}
                      {activity.type === 'flashcard' && (
                        <>
                          {activity.details.main_topic && (
                            <p><span className="font-medium">Topic:</span> {activity.details.main_topic}</p>
                          )}
                          {activity.details.count && (
                            <p><span className="font-medium">Cards:</span> {activity.details.count}</p>
                          )}
                          {activity.details.sample && activity.details.sample.length > 0 && (
                            <p><span className="font-medium">Sample:</span> "{activity.details.sample[0]}"</p>
                          )}
                        </>
                      )}
                      
                      {/* Test activity details */}
                      {activity.type === 'test' && (
                        <>
                          {activity.details.main_topic && (
                            <p><span className="font-medium">Topic:</span> {activity.details.main_topic}</p>
                          )}
                          {activity.details.count && (
                            <p><span className="font-medium">Questions:</span> {activity.details.count}</p>
                          )}
                          {activity.details.sample && activity.details.sample.length > 0 && (
                            <p><span className="font-medium">Sample:</span> "{activity.details.sample[0]}"</p>
                          )}
                        </>
                      )}
                      
                      {/* Concept map activity details */}
                      {activity.type === 'concept' && (
                        <>
                          {activity.details.main_topic && (
                            <p><span className="font-medium">Topic:</span> {activity.details.main_topic}</p>
                          )}
                          {activity.details.subtopics && activity.details.subtopics.length > 0 && (
                            <p><span className="font-medium">Subtopics:</span> {activity.details.subtopics.slice(0, 2).join(', ')}{activity.details.subtopics.length > 2 ? '...' : ''}</p>
                          )}
                          {activity.details.new_topics && activity.details.new_topics.length > 0 && (
                            <p><span className="font-medium">Related topics:</span> {activity.details.new_topics.slice(0, 2).join(', ')}{activity.details.new_topics.length > 2 ? '...' : ''}</p>
                          )}
                        </>
                      )}
                    </div>
                  )}
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
