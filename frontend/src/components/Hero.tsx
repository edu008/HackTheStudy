
import { ArrowRight } from 'lucide-react';
import { Button } from "@/components/ui/button";

const Hero = () => {
  return (
    <div className="relative overflow-hidden pt-32 pb-24 md:pt-40 md:pb-32">
      {/* Background gradient */}
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_center,rgba(var(--primary-rgb),0.05),transparent_50%)]"></div>
      
      <div className="container max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center space-y-10">
          <div className="space-y-6 max-w-3xl mx-auto">
            <div className="inline-flex items-center px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-sm text-primary animate-fade-in">
              <span className="relative px-2">Optimiere dein Studium mit KI</span>
            </div>
            
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-balance animate-slide-down">
              Prüfungsvorbereitung <span className="text-gradient">neu gedacht</span>
            </h1>
            
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto text-balance animate-fade-in">
              Wandle alte Moodle-Prüfungen in personalisierte Lernmaterialien um und trainiere mit KI-generierten Testfragen.
            </p>
          </div>
          
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-3 animate-slide-up">
            <Button size="lg" className="w-full sm:w-auto group">
              <span>Starte jetzt</span>
              <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Button>
            <Button variant="outline" size="lg" className="w-full sm:w-auto">
              Wie es funktioniert
            </Button>
          </div>
        </div>
        
        {/* Hero image */}
        <div className="mt-16 md:mt-24 relative mx-auto max-w-5xl animate-blur-in">
          <div className="relative rounded-2xl overflow-hidden shadow-hard border border-border/50">
            <div className="absolute inset-0 bg-gradient-to-t from-background/80 to-transparent z-10"></div>
            <div className="glass-card rounded-2xl w-full aspect-[16/9] flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30">
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-6 p-8 w-full max-w-4xl">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div 
                      key={i} 
                      className="bg-white dark:bg-gray-800 rounded-xl shadow-soft p-6 hover-card border border-border/50 flex flex-col justify-between"
                      style={{ animationDelay: `${i * 100}ms` }}
                    >
                      <div className="h-4 w-2/3 bg-primary/10 rounded mb-3"></div>
                      <div className="space-y-2">
                        <div className="h-3 w-full bg-gray-200 dark:bg-gray-700 rounded"></div>
                        <div className="h-3 w-4/5 bg-gray-200 dark:bg-gray-700 rounded"></div>
                        <div className="h-3 w-2/3 bg-gray-200 dark:bg-gray-700 rounded"></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
          
          {/* Floating elements */}
          <div className="absolute -top-8 -right-8 w-40 h-40 bg-primary/5 rounded-full blur-3xl"></div>
          <div className="absolute -bottom-8 -left-8 w-40 h-40 bg-blue-500/5 rounded-full blur-3xl"></div>
        </div>
      </div>
    </div>
  );
};

export default Hero;
