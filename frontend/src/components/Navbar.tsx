import { useState, useEffect, useRef } from 'react';
import { Button } from "@/components/ui/button";
import { GraduationCap, Menu, X } from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

interface Flashcard {
  id: number;
  question: string;
  answer: string;
}

interface Question {
  id: number;
  text: string;
  options: string[];
  correctAnswer: number;
  explanation?: string;  // Make explanation optional to support both old and new questions
}

interface UploadResponse {
  success: boolean;
  message: string;
  flashcards: Flashcard[];
  questions: Question[];
}

interface NavbarProps {
  onUploadSuccess?: (data: UploadResponse) => void;
}

const Navbar = ({ onUploadSuccess }: NavbarProps) => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null); // Ref für den Datei-Input

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToSection = (sectionId: string) => {
    const section = document.getElementById(sectionId);
    if (section) {
      section.scrollIntoView({ behavior: 'smooth' });
    }
    setIsMenuOpen(false);
  };

  const handleGetStartedClick = () => {
    fileInputRef.current?.click(); // Öffnet den Datei-Dialog
    setIsMenuOpen(false); // Schließt das mobile Menü
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files[0];
    if (file && onUploadSuccess) {
      // Hier simulieren wir die Logik von ExamUploader
      const formData = new FormData();
      formData.append('file', file);

      try {
        console.log('DEBUG: Navbar sending file to backend:', file.name);
        const response = await fetch(`${API_URL}/api/upload`, {
          method: 'POST',
          body: formData,
          credentials: 'include', // Entspricht withCredentials: true
        });
        const data = await response.json();
        console.log('DEBUG: Navbar received response from backend:', data);
        console.log('DEBUG: Navbar flashcards:', data.flashcards);
        console.log('DEBUG: Navbar questions:', data.questions);
        if (data.success) {
          console.log('DEBUG: Navbar calling onUploadSuccess with data');
          onUploadSuccess(data); // Übergibt die Antwort an Index
        } else {
          console.error('Upload fehlgeschlagen:', data.message);
        }
      } catch (error) {
        console.error('Fehler beim Upload:', error);
      }
    }
    // Reset des Inputs, damit dieselbe Datei erneut hochgeladen werden kann
    event.target.value = '';
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
            <button 
              onClick={() => scrollToSection('hero')} 
              className="flex items-center space-x-2 text-xl font-semibold"
            >
              <GraduationCap className="h-6 w-6 text-primary" />
              <span className="animate-fade-in">HackTheStudy</span>
            </button>
          </div>
          
          {/* Desktop Navigation */}
          <div className="hidden md:block">
            <div className="flex items-center space-x-6">
              <button 
                onClick={() => scrollToSection('hero')} 
                className="text-muted-foreground hover:text-foreground transition-colors duration-200"
              >
                Home
              </button>
              <button 
                onClick={() => scrollToSection('flashcards')} 
                className="text-muted-foreground hover:text-foreground transition-colors duration-200"
              >
                Flashcards
              </button>
              <button 
                onClick={() => scrollToSection('test-simulator')} 
                className="text-muted-foreground hover:text-foreground transition-colors duration-200"
              >
                Test Simulator
              </button>
              <Button 
                size="sm" 
                className="ml-6 animate-fade-in" 
                onClick={handleGetStartedClick}
              >
                Get Started
              </Button>
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
            <button 
              onClick={() => scrollToSection('hero')} 
              className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
            >
              Home
            </button>
            <button 
              onClick={() => scrollToSection('flashcards')} 
              className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
            >
              Flashcards
            </button>
            <button 
              onClick={() => scrollToSection('test-simulator')} 
              className="block px-3 py-2 text-foreground rounded-md hover:bg-secondary transition-colors duration-200"
            >
              Test Simulator
            </button>
            <Button 
              size="sm" 
              className="mt-2 w-full" 
              onClick={handleGetStartedClick}
            >
              Get Started
            </Button>
          </div>
        </div>
      )}
      
      {/* Versteckter Datei-Input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden"
        accept=".pdf,.doc,.docx,.txt" // Anpassbare Dateitypen
      />
    </nav>
  );
};

export default Navbar;
