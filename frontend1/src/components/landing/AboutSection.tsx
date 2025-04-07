import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowLeft, ArrowRight, ArrowUp, Upload, Brain, BookOpen, FlaskConical, GraduationCap, CheckCircle } from "lucide-react";
import { useTranslation } from 'react-i18next';

interface AboutSectionProps {
  onStartClick: () => void;
  onBackClick: () => void;
}

const AboutSection = ({ onStartClick, onBackClick }: AboutSectionProps) => {
  const { t } = useTranslation();
  
  const features = [
    {
      icon: Upload,
      titleKey: "landing.about.features.upload.title",
      descriptionKey: "landing.about.features.upload.description"
    },
    {
      icon: Brain,
      titleKey: "landing.about.features.analysis.title",
      descriptionKey: "landing.about.features.analysis.description"
    },
    {
      icon: BookOpen,
      titleKey: "landing.about.features.generate.title",
      descriptionKey: "landing.about.features.generate.description"
    },
    {
      icon: FlaskConical,
      titleKey: "landing.about.features.test.title",
      descriptionKey: "landing.about.features.test.description"
    },
    {
      icon: GraduationCap,
      titleKey: "landing.about.features.learn.title",
      descriptionKey: "landing.about.features.learn.description"
    }
  ];

  return (
    <div className="container mx-auto px-6">
      <div className="text-center max-w-3xl mx-auto mb-16">
        <h2 className="text-3xl md:text-4xl font-bold mb-4 text-gray-800">{t('landing.about.title')}</h2>
        <p className="text-lg text-gray-600">
          {t('landing.about.subtitle')}
        </p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto">
        {features.map((feature, index) => (
          <div 
            key={index} 
            className="relative transition-all group hover:scale-105 duration-300"
            style={{ animationDelay: `${index * 100}ms` }}
          >
            <Card className="h-full border-blue-100 bg-white shadow-md hover:shadow-xl">
              <CardContent className="p-6 space-y-4">
                <div className="p-3 rounded-lg bg-blue-50 text-blue-500 w-fit">
                  <feature.icon className="h-6 w-6" />
                </div>
                
                <h3 className="text-xl font-semibold text-gray-800">
                  {t(feature.titleKey)}
                </h3>
                
                <p className="text-gray-600 text-sm">
                  {t(feature.descriptionKey)}
                </p>
                
                <div className="pt-2">
                  <div className="text-xs font-medium text-blue-500 flex items-center">
                    <CheckCircle className="h-3 w-3 mr-1" /> {t('landing.about.included')}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        ))}
      </div>
      
      {/* CTA Section */}
      <div className="mt-20 text-center">
        <h3 className="text-2xl md:text-3xl font-bold mb-8 text-gray-800">{t('landing.about.cta.title')}</h3>
        
        <div className="flex flex-col sm:flex-row justify-center gap-6">
          <Button onClick={onBackClick} variant="outline" className="px-8 py-6 rounded-full">
            <ArrowUp className="mr-2 h-5 w-5" />
            {t('landing.about.cta.back')}
          </Button>
          
          <Button onClick={onStartClick} className="px-8 py-6 rounded-full bg-blue-500 hover:bg-blue-600">
            {t('landing.about.cta.start')}
            <ArrowRight className="ml-2 h-5 w-5" />
          </Button>
        </div>
      </div>
    </div>
  );
};

export default AboutSection;