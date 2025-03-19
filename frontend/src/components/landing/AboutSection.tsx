import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowLeft, ArrowRight, ArrowUp, Upload, Brain, BookOpen, FlaskConical, GraduationCap, CheckCircle } from "lucide-react";

interface AboutSectionProps {
  onStartClick: () => void;
  onBackClick: () => void;
}

const AboutSection = ({ onStartClick, onBackClick }: AboutSectionProps) => {
  const features = [
    {
      icon: Upload,
      title: "Unterlagen hochladen",
      description: "Lade deine Skripte, Vorlesungsnotizen oder Lehrbücher hoch. Unsere KI verarbeitet verschiedene Formate und extrahiert die wichtigsten Informationen."
    },
    {
      icon: Brain,
      title: "KI-Analyse",
      description: "Unsere fortschrittliche KI analysiert deine Unterlagen, identifiziert Schlüsselkonzepte und erstellt ein Konzeptnetzwerk für besseres Verständnis."
    },
    {
      icon: BookOpen,
      title: "Lernmaterialien generieren",
      description: "Mit nur einem Klick erstellst du personalisierte Karteikarten und Testfragen zu den wichtigsten Themen deiner Unterlagen."
    },
    {
      icon: FlaskConical,
      title: "Wissen testen",
      description: "Nutze den Testmodus, um dein Wissen zu überprüfen und Wissenslücken zu identifizieren, mit automatischer Anpassung an deine Fortschritte."
    },
    {
      icon: GraduationCap,
      title: "Kontinuierliches Lernen",
      description: "Generiere zusätzliche Karteikarten oder Testfragen zu den Themen, die dir noch Schwierigkeiten bereiten, und vertiefe dein Verständnis."
    }
  ];

  return (
    <div className="container mx-auto px-6">
      <div className="text-center max-w-3xl mx-auto mb-16">
        <h2 className="text-3xl md:text-4xl font-bold mb-4 text-gray-800">Wie HackTheStudy funktioniert</h2>
        <p className="text-lg text-gray-600">
          Revolutioniere dein Lernen in wenigen einfachen Schritten und erreiche mehr mit weniger Aufwand.
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
                  {feature.title}
                </h3>
                
                <p className="text-gray-600 text-sm">
                  {feature.description}
                </p>
                
                <div className="pt-2">
                  <div className="text-xs font-medium text-blue-500 flex items-center">
                    <CheckCircle className="h-3 w-3 mr-1" /> Enthalten in allen Plänen
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        ))}
      </div>
      
      {/* CTA Section */}
      <div className="mt-20 text-center">
        <div className="max-w-2xl mx-auto p-8 rounded-xl bg-blue-50 border border-blue-100">
          <h3 className="text-2xl font-bold mb-4 text-gray-800">Bereit, dein Lernen zu revolutionieren?</h3>
          <p className="text-gray-600 mb-8">
            Melde dich noch heute an und beginne mit einer effektiveren Lernmethode.
          </p>
          
          <div className="flex flex-wrap justify-center gap-4">
            <Button 
              size="lg" 
              className="rounded-full px-6 py-6 bg-blue-500 hover:bg-blue-600 transition-all duration-300 shadow-md hover:shadow-lg border-0"
              onClick={onStartClick}
            >
              Jetzt anmelden und loslegen
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            
            <Button 
              variant="outline" 
              size="lg" 
              className="rounded-full px-6 py-6 border-2 border-blue-200 text-blue-600 hover:bg-blue-50 transition-all duration-300 gap-2"
              onClick={onBackClick}
            >
              <ArrowUp className="h-4 w-4" />
              Zurück zur Startseite
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AboutSection;