import React, { useState, useEffect } from 'react';
import { Button } from "@/components/ui/button";
import { Sparkles, ArrowRight, Info } from "lucide-react";

interface HeroSectionProps {
  onStartClick: () => void;
  onLearnMoreClick: () => void;
}

const HeroSection = ({ onStartClick, onLearnMoreClick }: HeroSectionProps) => {
  const [animate, setAnimate] = useState(false);
  
  useEffect(() => {
    // Animation starten nach dem ersten Rendering
    setAnimate(true);
  }, []);

  return (
    <div className="container mx-auto px-6 h-full flex items-center">
      <div className="w-full">
        {/* Hero Content */}
        <div className="relative flex flex-col justify-center items-center">
          <div className={`text-center transition-all duration-1000 transform ${animate ? 'translate-y-0 opacity-100' : 'translate-y-10 opacity-0'}`}>
            <div className="inline-flex items-center px-4 py-2 mb-6 rounded-full bg-blue-50 text-blue-500 border border-blue-100">
              <Sparkles className="h-4 w-4 mr-2" />
              <span className="text-sm font-medium">Die intelligente Lernplattform</span>
            </div>
            
            <h1 className="text-5xl md:text-7xl font-bold mb-8 tracking-tight text-gray-800">
              Lerne intelligenter<br />mit <span className="text-blue-500">HackTheStudy</span>
            </h1>
            
            <p className="text-xl md:text-2xl text-gray-600 max-w-3xl mx-auto mb-12 leading-relaxed">
              Revolutioniere dein Lernen mit KI-unterstützten Karteikarten, dynamischen Tests und umfassenden Konzeptanalysen.
            </p>
            
            <div className="flex flex-col sm:flex-row gap-5 justify-center mb-20">
              <Button 
                size="lg" 
                className="rounded-full px-8 py-6 text-lg bg-blue-500 hover:bg-blue-600 transition-all duration-300 shadow-lg hover:shadow-xl border-0"
                onClick={onStartClick}
              >
                Jetzt starten <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
              <Button 
                variant="outline" 
                size="lg" 
                className="rounded-full px-8 py-6 text-lg border-2 border-blue-200 text-blue-600 hover:bg-blue-50 transition-all duration-300"
                onClick={onLearnMoreClick}
              >
                Mehr erfahren <Info className="ml-2 h-5 w-5" />
              </Button>
            </div>
          </div>
        </div>
        
        {/* Stats Section */}
        <div className={`grid grid-cols-2 md:grid-cols-4 gap-8 max-w-5xl mx-auto transition-all duration-1000 transform ${animate ? 'translate-y-0 opacity-100' : 'translate-y-10 opacity-0'}`}
             style={{ transitionDelay: '300ms' }}>
          {stats.map((stat, index) => (
            <div key={index} className="text-center">
              <p className="text-3xl md:text-4xl font-bold text-blue-500">{stat.value}</p>
              <p className="text-sm text-gray-500">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// Stats data
const stats = [
  { value: '500+', label: 'Aktive Nutzer' },
  { value: '12K+', label: 'Erstellte Karteikarten' },
  { value: '95%', label: 'Zufriedene Nutzer' },
  { value: '24/7', label: 'Support' },
];

export default HeroSection;
