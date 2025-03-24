import { useState, useEffect } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, GraduationCap, RefreshCw, AlertCircle, Loader2, Coins } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Flashcard {
  id: string;
  question: string;
  answer: string;
}

interface TokenInfo {
  inputTokens: number;
  outputTokens: number;
  cost: number;
}

interface FlashcardGeneratorProps {
  flashcards?: Flashcard[];
  onGenerateMore?: () => void;
  isGenerating?: boolean;
  tokenInfo?: TokenInfo;
}

const FlashcardGenerator = ({ 
  flashcards = [], 
  onGenerateMore,
  isGenerating = false,
  tokenInfo
}: FlashcardGeneratorProps) => {
  const [cards, setCards] = useState<Flashcard[]>(flashcards);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const { t } = useTranslation();

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
        
        // Scroll Effekt hinzufügen, um die neue Karte zu markieren
        setTimeout(() => {
          const cardIndicators = document.querySelectorAll('.card-indicator');
          if (cardIndicators && cardIndicators[currentCount]) {
            cardIndicators[currentCount].scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            // Visuellen Effekt hinzufügen, um die neue Karte hervorzuheben
            const indicator = cardIndicators[currentCount] as HTMLElement;
            if (indicator) {
              indicator.classList.add('pulse-animation');
              setTimeout(() => {
                indicator.classList.remove('pulse-animation');
              }, 2000);
            }
          }
        }, 300);
      } else {
        // Initial load or complete replacement
        setCards(flashcards);
        
        // Behalte den aktuellen Index bei, falls es nicht die erste Ladung ist
        // und der aktuelle Index noch gültig ist
        if (cards.length > 0 && currentCardIndex < flashcards.length) {
          // Behalte den aktuellen Index
        } else {
          // Zurück zur ersten Karte
          setCurrentCardIndex(0);
        }
        setIsFlipped(false);
      }
    }
  }, [flashcards]);

  // Scrolle zur aktuellen Karte, wenn sich der Index ändert
  useEffect(() => {
    // Scrolle zur aktuellen Karte
    setTimeout(() => {
      const cardIndicators = document.querySelectorAll('.card-indicator');
      if (cardIndicators && cardIndicators[currentCardIndex]) {
        cardIndicators[currentCardIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);
  }, [currentCardIndex]);

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
    <section className="py-14 md:py-20 bg-white">
      <div className="container mx-auto">
        <div className="text-center mb-12 space-y-4">
          <h2 className="text-3xl md:text-4xl font-bold animate-fade-in">
            <GraduationCap className="inline-block mr-2 h-8 w-8 text-blue-500" />
            {t('flashcards.title')}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto animate-fade-in">
            {t('flashcards.description')}
          </p>
        </div>
        
        <div className="flex flex-col md:flex-row gap-6">
          <div className="flex-1 md:max-w-4xl">
            {cards.length > 0 ? (
              <>
                <div className="relative mb-6 h-[300px] sm:h-[400px] perspective-1000 flex flex-col">
                  <div 
                    className={`relative w-full h-full rounded-xl border border-border/50 shadow-soft bg-background flex items-center justify-center backface-hidden transform-style-3d transition-all duration-700 cursor-pointer ${
                      isFlipped ? 'rotate-y-180' : ''
                    }`}
                    onClick={handleFlip}
                  >
                    {/* Vorderseite */}
                    <div className={`absolute inset-0 p-8 flex flex-col space-y-4 items-center backface-hidden ${isFlipped ? 'invisible' : ''}`}>
                      <span className="text-xs text-muted-foreground uppercase tracking-widest font-medium">
                        {t('flashcards.front')}
                      </span>
                      <div className="text-lg sm:text-xl text-center max-w-2xl">
                        {cards[currentCardIndex]?.question}
                      </div>
                      <div className="absolute bottom-4 text-xs text-muted-foreground">
                        {t('flashcards.clickToFlip')}
                      </div>
                    </div>
                    
                    {/* Rückseite */}
                    <div className={`absolute inset-0 p-8 flex flex-col space-y-4 items-center backface-hidden rotate-y-180 ${!isFlipped ? 'invisible' : ''}`}>
                      <span className="text-xs text-muted-foreground uppercase tracking-widest font-medium">
                        {t('flashcards.back')}
                      </span>
                      <div className="text-lg sm:text-xl text-center max-w-2xl">
                        {cards[currentCardIndex]?.answer}
                      </div>
                      <div className="absolute bottom-4 text-xs text-muted-foreground">
                        {t('flashcards.clickToFlip')}
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="flex items-center justify-center space-x-4 mb-8">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handlePrevious}
                    disabled={currentCardIndex === 0}
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </Button>
                  
                  <div className="flex items-center space-x-1.5 max-w-[250px] overflow-x-auto py-2 px-4 hide-scrollbar">
                    {cards.map((_, index) => (
                      <div 
                        key={index}
                        className={`card-indicator w-2 h-2 rounded-full transition-all ${
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
                {t('flashcards.noCardsAvailable')}
              </div>
            )}
          </div>
          
          <div className="w-full md:w-64 flex flex-col space-y-4">
            <Card className="border border-border/50 shadow-soft">
              <CardContent className="pt-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{t('flashcards.total')}</span>
                    <span className="text-sm">{cards.length} {t('flashcards.cards')}</span>
                  </div>
                  
                  {tokenInfo && (
                    <div className="border-t pt-3 mt-3">
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-1.5">
                          <Coins className="h-3.5 w-3.5 text-amber-500" />
                          <span className="text-xs font-medium">{t('flashcards.tokenUsage')}</span>
                        </div>
                        <span className="text-xs font-medium text-amber-600">{tokenInfo.cost} Credits</span>
                      </div>
                      <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                        <span className="text-xs text-muted-foreground">{t('flashcards.input')}:</span>
                        <span className="text-xs text-right">{tokenInfo.inputTokens}</span>
                        <span className="text-xs text-muted-foreground">{t('flashcards.output')}:</span>
                        <span className="text-xs text-right">{tokenInfo.outputTokens}</span>
                      </div>
                    </div>
                  )}
                  
                  {cards.length === 0 && (
                    <div className="p-4 bg-amber-50 dark:bg-amber-950/20 rounded-lg mt-4">
                      <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
                        <AlertCircle className="h-4 w-4" />
                        <span className="text-xs font-medium">{t('flashcards.noCardsAvailable')}</span>
                      </div>
                      <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                        {t('flashcards.uploadFirst')}
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
                        {t('flashcards.generating')}
                      </>
                    ) : (
                      t('flashcards.generateMore')
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
      
      {/* CSS für die Animation */}
      <style>
        {`
        @keyframes pulse {
          0% { transform: scale(1); }
          50% { transform: scale(1.5); }
          100% { transform: scale(1); }
        }
        
        .pulse-animation {
          animation: pulse 0.5s ease-in-out 3;
        }
        `}
      </style>
    </section>
  );
};

export default FlashcardGenerator;
