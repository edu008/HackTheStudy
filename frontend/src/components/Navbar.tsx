import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { GraduationCap, Menu, X, History, CreditCard, LogOut } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useTranslation } from 'react-i18next';
import LanguageSelector from './LanguageSelector';
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
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyKey, setHistoryKey] = useState(Date.now());
  const { user, signOut, refreshUserCredits } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  useEffect(() => {
    const updateCredits = async () => {
      if (user) {
        const lastUpdateTime = parseInt(localStorage.getItem('last_nav_credit_update') || '0');
        const currentTime = Date.now();
        
        if (currentTime - lastUpdateTime > 60000) {
          await refreshUserCredits();
          localStorage.setItem('last_nav_credit_update', currentTime.toString());
        }
      }
    };

    updateCredits();
  }, [refreshUserCredits, user]);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (user) {
      const creditUpdateInterval = setInterval(() => {
        refreshUserCredits();
      }, 120000);

      return () => {
        clearInterval(creditUpdateInterval);
      };
    }
  }, [user, refreshUserCredits]);

  const handleSignOut = () => {
    signOut();
    navigate('/');
  };

  const handleOpenHistory = () => {
    setHistoryKey(Date.now());  // Force re-render of UserHistory
    setHistoryOpen(true);
    refreshUserCredits();
  };

  return (
    <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${isScrolled ? 'bg-background/70 backdrop-blur-lg shadow-sm' : 'bg-transparent'}`}>
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo and Nav Links - Desktop */}
          <div className="flex items-center">
            <Link to="/" className="flex items-center space-x-2">
              <GraduationCap className="h-8 w-8 text-primary" />
              <span className="text-xl font-bold">HackTheStudy</span>
            </Link>
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center space-x-4">
            {user ? (
              <>
                <div className="flex items-center space-x-1">
                  <div className="text-sm font-medium">
                    {t('navigation.credits')}: {user.credits}
                  </div>
                </div>

                <LanguageSelector />

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                      <Avatar className="h-8 w-8">
                        <AvatarImage src={user.avatar} alt={user.name} />
                        <AvatarFallback>{user.name.charAt(0)}</AvatarFallback>
                      </Avatar>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => navigate('/dashboard')}>
                      {t('navigation.dashboard')}
                    </DropdownMenuItem>
                    
                    <DropdownMenuItem onClick={() => navigate('/payment')}>
                      <CreditCard className="h-4 w-4 mr-2" />
                      {t('navigation.buyCredits')}
                    </DropdownMenuItem>
                    
                    <DropdownMenuItem onClick={handleOpenHistory}>
                      <History className="h-4 w-4 mr-2" />
                      {t('navigation.history')}
                    </DropdownMenuItem>
                    
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={signOut}>
                      <LogOut className="h-4 w-4 mr-2" />
                      {t('navigation.signOut')}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                
                {/* History Sheet - wird über handleOpenHistory geöffnet */}
                <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                  <SheetContent side="right" onCloseAutoFocus={() => {}}>
                    <SheetHeader>
                      <SheetTitle>{t('navigation.history')}</SheetTitle>
                      <SheetDescription>
                        {t('common.loading')}
                      </SheetDescription>
                    </SheetHeader>
                    <UserHistory key={historyKey} />
                  </SheetContent>
                </Sheet>
              </>
            ) : (
              <>
                <LanguageSelector />
              </>
            )}
          </nav>

          {/* Mobile Menu Button */}
          <div className="flex md:hidden">
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="text-foreground"
            >
              {isMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Mobile Navigation Menu */}
      {isMenuOpen && (
        <div className="md:hidden bg-background border-b">
          <div className="container mx-auto px-4 py-4 space-y-3">
            {user ? (
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <Avatar className="h-10 w-10">
                      <AvatarImage src={user.avatar} alt={user.name} />
                      <AvatarFallback>{user.name.charAt(0)}</AvatarFallback>
                    </Avatar>
                    <div>
                      <p className="text-sm font-medium">{user.name}</p>
                      <p className="text-xs text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                  <div>
                    <p className="text-sm font-medium">{t('navigation.credits')}: {user.credits}</p>
                  </div>
                </div>

                <hr />

                <Link
                  to="/dashboard"
                  className="flex items-center rounded-md px-3 py-2 text-sm hover:bg-accent"
                  onClick={() => setIsMenuOpen(false)}
                >
                  {t('navigation.dashboard')}
                </Link>
                
                <Link
                  to="/payment"
                  className="flex items-center rounded-md px-3 py-2 text-sm hover:bg-accent"
                  onClick={() => setIsMenuOpen(false)}
                >
                  {t('navigation.buyCredits')}
                </Link>
                <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                  <SheetTrigger asChild>
                    <Button variant="outline" size="sm" className="w-full justify-start" onClick={handleOpenHistory}>
                      <History className="h-4 w-4 mr-2" />
                      {t('navigation.history')}
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="right" onCloseAutoFocus={() => {}}>
                    <SheetHeader>
                      <SheetTitle>{t('navigation.history')}</SheetTitle>
                      <SheetDescription>
                        {t('common.loading')}
                      </SheetDescription>
                    </SheetHeader>
                    <UserHistory key={historyKey} />
                  </SheetContent>
                </Sheet>
                
                <div className="flex items-center space-x-2 mt-2">
                  <LanguageSelector />
                  <Button 
                    onClick={() => {
                      signOut();
                      setIsMenuOpen(false);
                    }} 
                    variant="destructive" 
                    className="w-full"
                  >
                    <LogOut className="h-4 w-4 mr-2" />
                    {t('navigation.signOut')}
                  </Button>
                </div>
              </>
            ) : (
              <div className="flex flex-col space-y-3">
                <LanguageSelector />
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
};

export default Navbar;