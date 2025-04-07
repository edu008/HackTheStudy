import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { GraduationCap, Menu, X, History, CreditCard, LogOut, User as UserIcon, CheckSquare } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useTranslation } from 'react-i18next';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import UserHistory from '@/components/UserHistory';

// Einfache LanguageSelector-Komponente
const LanguageSelector = () => {
  const { i18n } = useTranslation();
  
  const changeLanguage = (language: string) => {
    i18n.changeLanguage(language);
  };
  
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm">
          {i18n.language === 'en' ? 'EN' : 'DE'}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onClick={() => changeLanguage('de')}>
          Deutsch
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => changeLanguage('en')}>
          English
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

interface NavbarProps {
  onLoginClick?: () => void;
}

const Navbar = ({ onLoginClick }: NavbarProps) => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyKey, setHistoryKey] = useState(Date.now());
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

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

  const handleOpenHistory = () => {
    setHistoryKey(Date.now());  // Force re-render of UserHistory
    setHistoryOpen(true);
  };

  const refreshUserCredits = () => {
    // Platzhalter für die Aktualisierung der Benutzer-Credits
    // In einer echten App würde hier ein API-Aufruf erfolgen
    console.log('Aktualisiere Benutzer-Credits');
  };

  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map(part => part[0])
      .join('')
      .toUpperCase();
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
                    {t('navigation.credits', 'Credits')}: {user.credits}
                  </div>
                </div>

                <LanguageSelector />

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                      <Avatar className="h-8 w-8">
                        <AvatarImage src={user.avatar} alt={user.name} />
                        <AvatarFallback>{getInitials(user.name)}</AvatarFallback>
                      </Avatar>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => navigate('/dashboard')}>
                      {t('navigation.dashboard', 'Dashboard')}
                    </DropdownMenuItem>
                    
                    <DropdownMenuItem onClick={() => navigate('/payment')}>
                      <CreditCard className="h-4 w-4 mr-2" />
                      {t('navigation.buyCredits', 'Buy Credits')}
                    </DropdownMenuItem>
                    
                    <DropdownMenuItem onClick={handleOpenHistory}>
                      <History className="h-4 w-4 mr-2" />
                      {t('navigation.history', 'History')}
                    </DropdownMenuItem>
                    
                    <DropdownMenuItem onClick={() => navigate('/tasks')}>
                      <CheckSquare className="h-4 w-4 mr-2" />
                      {t('navigation.tasks', 'Tasks')}
                    </DropdownMenuItem>
                    
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={handleSignOut}>
                      <LogOut className="h-4 w-4 mr-2" />
                      {t('navigation.signOut', 'Sign Out')}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                
                {/* History Sheet */}
                <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                  <SheetContent side="right" onCloseAutoFocus={() => {}}>
                    <SheetHeader>
                      <SheetTitle>{t('navigation.history', 'History')}</SheetTitle>
                      <SheetDescription>
                        {t('common.loading', 'Loading...')}
                      </SheetDescription>
                    </SheetHeader>
                    <UserHistory key={historyKey} />
                  </SheetContent>
                </Sheet>
              </>
            ) : (
              <>
                <LanguageSelector />
                <Button 
                  size="sm" 
                  onClick={onLoginClick || (() => navigate('/signin'))}
                >
                  {t('navigation.signIn', 'Sign In')}
                </Button>
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
                      <AvatarFallback>{getInitials(user.name)}</AvatarFallback>
                    </Avatar>
                    <div>
                      <p className="text-sm font-medium">{user.name}</p>
                      <p className="text-xs text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                  <div>
                    <p className="text-sm font-medium">{t('navigation.credits', 'Credits')}: {user.credits}</p>
                  </div>
                </div>

                <hr />

                <Link
                  to="/dashboard"
                  className="flex items-center rounded-md px-3 py-2 text-sm hover:bg-accent"
                  onClick={() => setIsMenuOpen(false)}
                >
                  {t('navigation.dashboard', 'Dashboard')}
                </Link>
                
                <Link
                  to="/payment"
                  className="flex items-center rounded-md px-3 py-2 text-sm hover:bg-accent"
                  onClick={() => setIsMenuOpen(false)}
                >
                  {t('navigation.buyCredits', 'Buy Credits')}
                </Link>
                <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                  <SheetTrigger asChild>
                    <Button variant="outline" size="sm" className="w-full justify-start" onClick={handleOpenHistory}>
                      <History className="h-4 w-4 mr-2" />
                      {t('navigation.history', 'History')}
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="right" onCloseAutoFocus={() => {}}>
                    <SheetHeader>
                      <SheetTitle>{t('navigation.history', 'History')}</SheetTitle>
                      <SheetDescription>
                        {t('common.loading', 'Loading...')}
                      </SheetDescription>
                    </SheetHeader>
                    <UserHistory key={historyKey} />
                  </SheetContent>
                </Sheet>
                
                <div className="flex items-center space-x-2 mt-2">
                  <LanguageSelector />
                  <Button 
                    onClick={() => {
                      handleSignOut();
                      setIsMenuOpen(false);
                    }} 
                    variant="destructive" 
                    className="w-full"
                  >
                    <LogOut className="h-4 w-4 mr-2" />
                    {t('navigation.signOut', 'Sign Out')}
                  </Button>
                </div>
              </>
            ) : (
              <div className="flex flex-col space-y-3">
                <LanguageSelector />
                <Button 
                  onClick={() => {
                    if (onLoginClick) onLoginClick();
                    else navigate('/signin');
                    setIsMenuOpen(false);
                  }}
                >
                  {t('navigation.signIn', 'Sign In')}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
};

export default Navbar;
