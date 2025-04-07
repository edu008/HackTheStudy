import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";

// Landing Page Komponenten importieren
import HeroSection from '@/components/landing/HeroSection';
import AboutSection from '@/components/landing/AboutSection';
import LoginSection from '@/components/landing/LoginSection';

const Index = () => {
  // State für Landing Page Navigation
  const [currentView, setCurrentView] = useState('login'); // Starte mit Login-Ansicht
  
  // Auth-Kontext für Benutzerauthentifizierung
  const { user, isLoading, signIn } = useAuth();
  const navigate = useNavigate();
  
  // Refs für Scroll-Verhalten
  const heroSectionRef = useRef(null);
  const aboutSectionRef = useRef(null);
  const loginSectionRef = useRef(null);
  
  // Weiterleitung zur TaskPage, wenn Benutzer angemeldet ist
  useEffect(() => {
    if (user) {
      navigate('/tasks');
    }
  }, [user, navigate]);
  
  // Scrolle zur entsprechenden Sektion, wenn sich der View ändert
  useEffect(() => {
    if (currentView === 'login' && loginSectionRef.current) {
      loginSectionRef.current.scrollIntoView({ behavior: 'smooth' });
    } else if (currentView === 'about' && aboutSectionRef.current) {
      aboutSectionRef.current.scrollIntoView({ behavior: 'smooth' });
    } else if (currentView === 'hero' && heroSectionRef.current) {
      heroSectionRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentView]);
  
  // Funktion zum Zurückkehren zur Hero-Sektion
  const handleBackToHero = () => {
    setCurrentView('hero');
  };
  
  // Funktion für erfolgreiche Anmeldung - verwendet AuthContext
  const handleSignIn = async (provider) => {
    // Rufe die signIn-Funktion vom Auth-Kontext mit dem Provider auf
    await signIn(provider);
  };

  // Zeige Ladeindikator während der Authentifizierungsprüfung
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full mb-4 mx-auto"></div>
          <p className="text-lg">Wird geladen...</p>
        </div>
      </div>
    );
  }

  // Wenn Benutzer bereits angemeldet ist, sollte die useEffect-Hook ihn weiterleiten
  if (user) {
    return null;
  }

  return (
    // Landing page Layout ohne Navbar und Footer
    <div className="min-h-screen w-full flex flex-col bg-[#f0f7ff]">
      {/* Hero Section - Volle Höhe für initiale Ansicht */}
      <section 
        ref={heroSectionRef}
        className={`min-h-screen flex items-center justify-center bg-[#f0f7ff] py-20 ${currentView !== 'hero' ? 'h-auto' : ''}`}
        id="hero-section"
      >
        <div className="w-full">
          <HeroSection 
            onStartClick={() => setCurrentView('login')}
            onLearnMoreClick={() => setCurrentView('about')}
          />
        </div>
      </section>
      
      {/* About Section */}
      <section 
        ref={aboutSectionRef} 
        className={`min-h-screen py-20 flex items-center bg-[#f0f7ff] ${currentView === 'about' ? 'animate-fade-in' : ''}`}
        id="about-section"
      >
        <div className="w-full">
          <AboutSection 
            onStartClick={() => setCurrentView('login')}
            onBackClick={handleBackToHero}
          />
        </div>
      </section>
      
      {/* Login Section */}
      <section 
        ref={loginSectionRef} 
        className={`min-h-screen py-20 flex items-center justify-center bg-[#f0f7ff] ${currentView === 'login' ? 'animate-fade-in' : ''}`}
        id="login-section"
      >
        <div className="w-full">
          <LoginSection 
            onBackClick={handleBackToHero}
            onSignIn={handleSignIn}
          />
        </div>
      </section>
    </div>
  );
};

export default Index;
