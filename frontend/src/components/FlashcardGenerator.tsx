import { useState, useEffect } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, GraduationCap, RefreshCw, AlertCircle } from 'lucide-react';

interface Flashcard {
  id: string;
  question: string;
  answer: string;
}

interface FlashcardGeneratorProps {
  flashcards?: Flashcard[];
  onGenerateMore?: () => void;
  isGenerating?: boolean;
}

const FlashcardGenerator = ({ 
  flashcards = [], 
  onGenerateMore,
  isGenerating = false
}: FlashcardGeneratorProps) => {
  const [cards, setCards] = useState<Flashcard[]>(flashcards);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);

  useEffect(() => {
    // Reset wenn keine Flashcards vorhanden sind
    if (flashcards.length === 0) {
      setCards([]);
      setCurrentCardIndex(0);
      setIsFlipped(false);
    } else if (flashcards.length > 0) {
      // Check if these are new flashcards being added to existing ones
      if (cards.length > 0 && flashcards.length > cards.length) {
        // Store the current count before updating
        const currentCount = cards.length;
        
        // Update the cards
        setCards(flashcards);
        
        // Jump to the first new card (index is zero-based)
        setCurrentCardIndex(currentCount);
        setIsFlipped(false);
      } else {
        // Initial load or complete replacement
        setCards(flashcards);
        setCurrentCardIndex(0);
        setIsFlipped(false);
      }
    }
  }, [flashcards]);

  const handleNext = () => {
    if (currentCardIndex < cards.length - 1) {
      setCurrentCardIndex(prevIndex => prevIndex + 1);
      setIsFlipped(false);
    }
  };

  const handlePrevious = () => {
    if (currentCardIndex > 0) {
      setCurrentCardIndex(prevIndex => prevIndex - 1);
      setIsFlipped(false);
    }
  };

  const handleFlip = () => {
    setIsFlipped(prevState => !prevState);
  };

  const handleGenerateMore = () => {
    if (onGenerateMore) {
      onGenerateMore();
    }
  };
  
  return (
    <section id="flashcards" className="section-container bg-secondary/30">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12 space-y-4">
          <h2 className="text-3xl md:text-4xl font-bold animate-fade-in">
            KI-generierte Karteikarten
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto animate-fade-in">
            Aus deinen Prüfungen erstellt unsere KI optimal strukturierte Karteikarten, die dir beim Lernen helfen.
          </p>
        </div>
        
        <div className="flex flex-col md:flex-row gap-8 items-center">
          <div className="flex-1 w-full">
            {cards.length > 0 ? (
              <>
                <div className="relative mx-auto max-w-md perspective-1000">
                  <div 
                    className={`card-container relative w-full h-[320px] transition-transform duration-700 ${
                      isFlipped ? 'rotate-y-180' : ''
                    }`}
                    style={{ transformStyle: 'preserve-3d' }}
                    onClick={handleFlip}
                  >
                    {/* Front */}
                    <Card className={`absolute inset-0 rounded-xl shadow-medium p-6 border border-border/50 flex flex-col justify-between transition-all backface-hidden ${
                      isFlipped ? 'opacity-0' : 'opacity-100'
                    }`}>
                      <div className="flex justify-center mb-6">
                        <div className="px-3 py-1 rounded-full border border-primary/20 bg-primary/5 text-sm text-primary flex items-center gap-1">
                          <GraduationCap className="h-3.5 w-3.5" />
                          <span>Frage {currentCardIndex + 1} von {cards.length}</span>
                        </div>
                      </div>
                      <div className="flex-1 flex items-center justify-center">
                        <h3 className="text-xl font-medium text-center">
                          {cards[currentCardIndex]?.question.replace(/\*\*/g, '')}
                        </h3>
                      </div>
                      <div className="text-sm text-muted-foreground text-center">
                        Klicken zum Umdrehen
                      </div>
                    </Card>
                    
                    {/* Back */}
                    <Card className={`absolute inset-0 rounded-xl shadow-medium p-6 border border-border/50 flex flex-col justify-between transition-all backface-hidden rotate-y-180 ${
                      isFlipped ? 'opacity-100' : 'opacity-0'
                    }`}>
                      <div className="flex justify-center mb-4">
                        <div className="px-3 py-1 rounded-full border border-green-500/20 bg-green-500/5 text-sm text-green-600 dark:text-green-400">
                          Antwort
                        </div>
                      </div>
                      <div className="flex-1 flex items-center justify-center">
                        <p className="text-center">
                          {cards[currentCardIndex]?.answer.replace(/\*\*/g, '')}
                        </p>
                      </div>
                      <div className="text-sm text-muted-foreground text-center">
                        Klicken zum Umdrehen
                      </div>
                    </Card>
                  </div>
                </div>
                
                <div className="flex justify-between mt-6 max-w-md mx-auto">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handlePrevious}
                    disabled={currentCardIndex === 0}
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </Button>
                  
                  <div className="flex space-x-1 overflow-x-auto">
                    {cards.map((_, index) => (
                      <div 
                        key={index}
                        className={`w-2 h-2 rounded-full transition-all ${
                          index === currentCardIndex 
                            ? 'bg-primary w-4' 
                            : 'bg-primary/30'
                        }`}
                      />
                    ))}
                  </div>
                  
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handleNext}
                    disabled={currentCardIndex === cards.length - 1}
                  >
                    <ChevronRight className="h-5 w-5" />
                  </Button>
                </div>
              </>
            ) : (
              <div className="text-center text-muted-foreground">
                Keine Karteikarten verfügbar. Lade eine Datei hoch, um welche zu generieren.
              </div>
            )}
          </div>
          
          <div className="w-full md:w-64 flex flex-col space-y-4">
            <Card className="border border-border/50 shadow-soft">
              <CardContent className="pt-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Gesamt</span>
                    <span className="text-sm">{cards.length} Karten</span>
                  </div>
                  
                  {cards.length === 0 && (
                    <div className="p-4 bg-amber-50 dark:bg-amber-950/20 rounded-lg mt-4">
                      <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
                        <AlertCircle className="h-4 w-4" />
                        <span className="text-xs font-medium">Keine Karteikarten verfügbar</span>
                      </div>
                      <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                        Lade zuerst eine Prüfung hoch, um Karteikarten zu generieren.
                      </p>
                    </div>
                  )}
                  <Button 
                    className="w-full mt-6"
                    onClick={handleGenerateMore}
                    disabled={isGenerating}
                  >
                    {isGenerating ? (
                      <>
                        <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                        Generiere...
                      </>
                    ) : (
                      "Mehr generieren"
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </section>
  );
};

export default FlashcardGenerator;
