import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { GraduationCap, Menu, X, History, CreditCard, LogOut, User } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import UserHistory from '@/components/UserHistory';

interface NavbarProps {
  onLoginClick?: () => void;
}

const Navbar = ({ onLoginClick }: NavbarProps) => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleSignOut = () => {
    signOut();
    navigate('/');
  };

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
      isScrolled 
        ? "py-3 bg-white/80 dark:bg-black/80 backdrop-blur-lg shadow-soft" 
        : "py-5 bg-transparent"
    }`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center">
            <Link 
              to="/" 
              className="flex items-center space-x-2 text-xl font-semibold"
              onClick={(e) => {
                e.preventDefault();
                window.scrollTo(0, 0);
                window.location.href = '/';
              }}
            >
              <GraduationCap className="h-6 w-6 text-primary" />
              <span className="animate-fade-in">HackTheStudy</span>
            </Link>
          </div>
          
          {/* Desktop Navigation */}
          <div className="hidden md:block">
            <div className="flex items-center space-x-6">
              <Link 
                to="/" 
                className="text-muted-foreground hover:text-foreground transition-colors duration-200"
                onClick={(e) => {
                  e.preventDefault();
                  window.scrollTo(0, 0);
                  window.location.href = '/';
                }}
              >
                Home
              </Link>
              
              {user && (
                <>
                  <Link 
                    to="/#flashcards" 
                    className="text-muted-foreground hover:text-foreground transition-colors duration-200"
                    onClick={(e) => {
                      e.preventDefault();
                      const flashcardsElement = document.getElementById('flashcards');
                      if (flashcardsElement) {
                        flashcardsElement.scrollIntoView({ behavior: 'smooth' });
                      }
                    }}
                  >
                    Flashcards
                  </Link>
                  <Link 
                    to="/#test-simulator" 
                    className="text-muted-foreground hover:text-foreground transition-colors duration-200"
                    onClick={(e) => {
                      e.preventDefault();
                      const testSimulatorElement = document.getElementById('test-simulator');
                      if (testSimulatorElement) {
                        testSimulatorElement.scrollIntoView({ behavior: 'smooth' });
                      }
                    }}
                  >
                    Test Simulator
                  </Link>
                  <Link 
                    to="/#concept-mapper" 
                    className="text-muted-foreground hover:text-foreground transition-colors duration-200"
                    onClick={(e) => {
                      e.preventDefault();
                      const conceptMapperElement = document.getElementById('concept-mapper');
                      if (conceptMapperElement) {
                        conceptMapperElement.scrollIntoView({ behavior: 'smooth' });
                      }
                    }}
                  >
                    Mindmap
                  </Link>
                </>
              )}
              
              {user ? (
                <div className="flex items-center space-x-4">
                  <div className="text-sm font-medium">
                    Credits: {user.credits}
                  </div>
                  
                  <Sheet>
                    <SheetTrigger asChild>
                      <Button variant="outline" size="sm">
                        <History className="h-4 w-4 mr-2" />
                        History
                      </Button>
                    </SheetTrigger>
                    <SheetContent side="right">
                      <SheetHeader>
                        <SheetTitle>Your History</SheetTitle>
                        <SheetDescription>
                          Your recent activities on HackTheStudy
                        </SheetDescription>
                      </SheetHeader>
                      <UserHistory />
                    </SheetContent>
                  </Sheet>
                  
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Avatar className="h-8 w-8 cursor-pointer">
                        <AvatarImage src={user.avatar} alt={user.name} />
                        <AvatarFallback>{user.name.charAt(0)}</AvatarFallback>
                      </Avatar>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem className="cursor-pointer" onClick={() => navigate('/dashboard', { replace: true })}>
                        <User className="mr-2 h-4 w-4" />
                        Dashboard
                      </DropdownMenuItem>
                      <DropdownMenuItem className="cursor-pointer" onClick={() => navigate('/payment')}>
                        <CreditCard className="mr-2 h-4 w-4" />
                        Buy Credits
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem className="cursor-pointer" onClick={handleSignOut}>
                        <LogOut className="mr-2 h-4 w-4" />
                        Sign Out
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ) : (
                <Button size="sm" onClick={() => navigate('/signin')} className="ml-6 animate-fade-in">
                  Sign In
                </Button>
              )}
            </div>
          </div>
          
          {/* Mobile Navigation Toggle */}
          <div className="md:hidden">
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              aria-label="Toggle menu"
            >
              {isMenuOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </Button>
          </div>
        </div>
      </div>
      
      {/* Mobile Navigation Menu */}
      {isMenuOpen && (
        <div className="md:hidden absolute top-full left-0 right-0 bg-white/95 dark:bg-black/95 backdrop-blur-md shadow-medium border-t">
          <div className="px-4 pt-2 pb-4 space-y-3 flex flex-col">
            <Link 
              to="/" 
              className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
              onClick={(e) => {
                e.preventDefault();
                setIsMenuOpen(false);
                window.scrollTo(0, 0);
                window.location.href = '/';
              }}
            >
              Home
            </Link>
            {user && (
              <>
                <Link 
                  to="/#flashcards" 
                  className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
                  onClick={(e) => {
                    e.preventDefault();
                    setIsMenuOpen(false);
                    const flashcardsElement = document.getElementById('flashcards');
                    if (flashcardsElement) {
                      flashcardsElement.scrollIntoView({ behavior: 'smooth' });
                    }
                  }}
                >
                  Flashcards
                </Link>
                <Link 
                  to="/#test-simulator" 
                  className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
                  onClick={(e) => {
                    e.preventDefault();
                    setIsMenuOpen(false);
                    const testSimulatorElement = document.getElementById('test-simulator');
                    if (testSimulatorElement) {
                      testSimulatorElement.scrollIntoView({ behavior: 'smooth' });
                    }
                  }}
                >
                  Test Simulator
                </Link>
                <Link 
                  to="/#concept-mapper" 
                  className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
                  onClick={(e) => {
                    e.preventDefault();
                    setIsMenuOpen(false);
                    const conceptMapperElement = document.getElementById('concept-mapper');
                    if (conceptMapperElement) {
                      conceptMapperElement.scrollIntoView({ behavior: 'smooth' });
                    }
                  }}
                >
                  Mindmap
                </Link>
              </>
            )}
            
            {user ? (
              <>
                <div className="flex items-center justify-between px-3 py-2">
                  <div className="flex items-center space-x-2">
                    <Avatar className="h-8 w-8">
                      <AvatarImage src={user.avatar} alt={user.name} />
                      <AvatarFallback>{user.name.charAt(0)}</AvatarFallback>
                    </Avatar>
                    <span className="font-medium">{user.name}</span>
                  </div>
                  <div className="text-sm">Credits: {user.credits}</div>
                </div>
                <Link 
                  to="/dashboard" 
                  className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
                  onClick={(e) => {
                    e.preventDefault();
                    setIsMenuOpen(false);
                    navigate('/dashboard', { replace: true });
                  }}
                >
                  Dashboard
                </Link>
                <Link 
                  to="/payment" 
                  className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
                  onClick={() => setIsMenuOpen(false)}
                >
                  Buy Credits
                </Link>
                <Sheet>
                  <SheetTrigger asChild>
                    <Button variant="outline" size="sm" className="w-full justify-start">
                      <History className="h-4 w-4 mr-2" />
                      History
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="right">
                    <SheetHeader>
                      <SheetTitle>Your History</SheetTitle>
                      <SheetDescription>
                        Your recent activities on HackTheStudy
                      </SheetDescription>
                    </SheetHeader>
                    <UserHistory />
                  </SheetContent>
                </Sheet>
                <Button 
                  size="sm" 
                  variant="outline" 
                  className="justify-start"
                  onClick={() => {
                    handleSignOut();
                    setIsMenuOpen(false);
                  }}
                >
                  <LogOut className="h-4 w-4 mr-2" /> 
                  Sign Out
                </Button>
              </>
            ) : (
              <Button size="sm" className="mt-2 w-full" onClick={() => navigate('/signin')}>
                Sign In
              </Button>
            )}
          </div>
        </div>
      )}
    </nav>
  );
};

export default Navbar;