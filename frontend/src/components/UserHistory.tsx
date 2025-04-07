
import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { UploadCloud, Lightbulb, BookOpen, Network } from 'lucide-react';

interface HistoryItem {
  id: string;
  type: 'upload' | 'flashcard' | 'test' | 'concept';
  title: string;
  timestamp: string;
}

const UserHistory = () => {
  const { user } = useAuth();
  const [history, setHistory] = useState<HistoryItem[]>([]);

  useEffect(() => {
    // In a real app, this would fetch from an API
    // For demo, we'll generate mock history data
    if (user) {
      const mockHistory: HistoryItem[] = [
        {
          id: '1',
          type: 'upload',
          title: 'Calculus Exam 2022',
          timestamp: new Date(Date.now() - 3600000).toISOString() // 1 hour ago
        },
        {
          id: '2',
          type: 'flashcard',
          title: 'Machine Learning Concepts',
          timestamp: new Date(Date.now() - 86400000).toISOString() // 1 day ago
        },
        {
          id: '3',
          type: 'test',
          title: 'Physics Test Simulation',
          timestamp: new Date(Date.now() - 172800000).toISOString() // 2 days ago
        },
        {
          id: '4',
          type: 'concept',
          title: 'Chemistry Connections',
          timestamp: new Date(Date.now() - 259200000).toISOString() // 3 days ago
        },
        {
          id: '5',
          type: 'upload',
          title: 'Statistics Final Exam',
          timestamp: new Date(Date.now() - 345600000).toISOString() // 4 days ago
        }
      ];
      
      setHistory(mockHistory);
    }
  }, [user]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffInMs = now.getTime() - date.getTime();
    const diffInHours = diffInMs / (1000 * 60 * 60);
    
    if (diffInHours < 24) {
      return `${Math.floor(diffInHours)} hours ago`;
    } else {
      const diffInDays = diffInHours / 24;
      return `${Math.floor(diffInDays)} days ago`;
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
      default:
        return <UploadCloud className="h-5 w-5 text-blue-500" />;
    }
  };

  return (
    <div className="py-6">
      {!user ? (
        <div className="text-center py-10 text-muted-foreground">
          Please sign in to view your history
        </div>
      ) : history.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          No history available yet
        </div>
      ) : (
        <ScrollArea className="h-[400px]">
          <div className="space-y-6 pr-4">
            {history.map((item) => (
              <div key={item.id} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    {getActivityIcon(item.type)}
                    <div>
                      <h4 className="text-sm font-medium">{item.title}</h4>
                      <p className="text-xs text-muted-foreground">
                        {formatDate(item.timestamp)}
                      </p>
                    </div>
                  </div>
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
