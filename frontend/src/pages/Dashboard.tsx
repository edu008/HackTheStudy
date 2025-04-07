
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { CreditCard, Upload, Lightbulb, BookOpen, Network } from 'lucide-react';
import UserHistory from '@/components/UserHistory';

const Dashboard = () => {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && !user) {
      navigate('/signin');
    }
  }, [user, isLoading, navigate]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center">
        <div className="animate-pulse text-lg">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return null; // Redirect happens in useEffect
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* User Profile Card */}
          <Card className="md:col-span-1">
            <CardHeader className="text-center">
              <Avatar className="h-24 w-24 mx-auto">
                <AvatarImage src={user.avatar} alt={user.name} />
                <AvatarFallback>{user.name.charAt(0)}</AvatarFallback>
              </Avatar>
              <CardTitle className="mt-4">{user.name}</CardTitle>
              <CardDescription>{user.email}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex justify-between items-center py-2 border-b">
                <span className="font-medium">Credits</span>
                <span className="font-bold">{user.credits}</span>
              </div>
              <Button 
                variant="outline" 
                className="w-full mt-6" 
                onClick={() => navigate('/payment')}
              >
                <CreditCard className="mr-2 h-4 w-4" />
                Buy More Credits
              </Button>
            </CardContent>
          </Card>

          {/* User Activities and History */}
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>Activities</CardTitle>
              <CardDescription>Your recent activities on ExamMaster</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                <Button variant="outline" className="flex flex-col h-24 justify-center">
                  <Upload className="h-6 w-6 mb-2" />
                  <span>Upload Exam</span>
                </Button>
                <Button variant="outline" className="flex flex-col h-24 justify-center">
                  <Lightbulb className="h-6 w-6 mb-2" />
                  <span>Create Flashcards</span>
                </Button>
                <Button variant="outline" className="flex flex-col h-24 justify-center">
                  <BookOpen className="h-6 w-6 mb-2" />
                  <span>Test Simulator</span>
                </Button>
                <Button variant="outline" className="flex flex-col h-24 justify-center">
                  <Network className="h-6 w-6 mb-2" />
                  <span>Concept Mapper</span>
                </Button>
              </div>
              <div>
                <h3 className="text-lg font-medium mb-4">Recent History</h3>
                <UserHistory />
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default Dashboard;
