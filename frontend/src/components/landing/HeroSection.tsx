import React, { useState, useEffect } from 'react';
import { Button } from "@/components/ui/button";
import { Sparkles, ArrowRight, Info } from "lucide-react";
import { useTranslation } from 'react-i18next';

interface HeroSectionProps {
  onStartClick: () => void;
  onLearnMoreClick: () => void;
}

const HeroSection = ({ onStartClick, onLearnMoreClick }: HeroSectionProps) => {
  const [animate, setAnimate] = useState(false);
  const { t } = useTranslation();
  
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
              <span className="text-sm font-medium">{t('landing.hero.tagline')}</span>
            </div>
            
            <h1 className="text-5xl md:text-7xl font-bold mb-8 tracking-tight text-gray-800">
              {t('landing.hero.title1')}<br />{t('landing.hero.title2')} <span className="text-blue-500">HackTheStudy</span>
            </h1>
            
            <p className="text-xl md:text-2xl text-gray-600 max-w-3xl mx-auto mb-12 leading-relaxed">
              {t('landing.hero.description')}
            </p>
            
            <div className="flex flex-col sm:flex-row gap-5 justify-center mb-20">
              <Button 
                size="lg" 
                className="rounded-full px-8 py-6 text-lg bg-blue-500 hover:bg-blue-600 transition-all duration-300 shadow-lg hover:shadow-xl border-0"
                onClick={onStartClick}
              >
                {t('landing.hero.startButton')} <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
              <Button 
                variant="outline" 
                size="lg" 
                className="rounded-full px-8 py-6 text-lg border-2 border-blue-200 text-blue-600 hover:bg-blue-50 transition-all duration-300"
                onClick={onLearnMoreClick}
              >
                {t('landing.hero.learnMoreButton')} <Info className="ml-2 h-5 w-5" />
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
              <p className="text-sm text-gray-500">{t(stat.labelKey)}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// Stats data
const stats = [
  { value: '500+', labelKey: 'landing.hero.stats.users' },
  { value: '12K+', labelKey: 'landing.hero.stats.flashcards' },
  { value: '95%', labelKey: 'landing.hero.stats.satisfaction' },
  { value: '24/7', labelKey: 'landing.hero.stats.support' },
];

export default HeroSection;
