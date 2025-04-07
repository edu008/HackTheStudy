import { useState } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, GraduationCap, RefreshCw } from 'lucide-react';
import { Flashcard } from '@/types';

// Temporäre Beispielkarten für den Fall, dass keine initialFlashcards übergeben werden
const sampleFlashcards: Flashcard[] = [
  {
    id: "1",
    question: "Was ist der Unterschied zwischen Kompilator und Interpreter?",
    answer: "Ein Kompilator übersetzt den gesamten Quellcode in Maschinensprache vor der Ausführung, während ein Interpreter den Code Zeile für Zeile ausführt, ohne vorher alles zu kompilieren."
  },
  {
    id: "2",
    question: "Erklären Sie die Prinzipien der objektorientierten Programmierung.",
    answer: "Die Hauptprinzipien der OOP sind Abstraktion (Komplexitätsreduktion), Kapselung (Daten und Funktionen werden zusammengefasst), Vererbung (Eigenschaften können vererbt werden) und Polymorphismus (Objekten mit gleicher Schnittstelle können unterschiedliche Implementierungen haben)."
  },
  {
    id: "3",
    question: "Was ist das OSI-Modell und welche Schichten hat es?",
    answer: "Das OSI-Modell ist ein Referenzmodell für Netzwerkprotokolle mit 7 Schichten: Physikalische Schicht, Sicherungsschicht, Netzwerkschicht, Transportschicht, Sitzungsschicht, Darstellungsschicht und Anwendungsschicht."
  },
];

interface FlashcardGeneratorProps {
  initialFlashcards?: Flashcard[];
}

const FlashcardGenerator: React.FC<FlashcardGeneratorProps> = ({ initialFlashcards }) => {
  const [cards, setCards] = useState<Flashcard[]>(initialFlashcards || sampleFlashcards);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

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
    setIsGenerating(true);
    
    // Simulate generating new flashcards
    setTimeout(() => {
      const newCards = [
        ...cards,
        {
          id: String(cards.length + 1),
          question: "Was ist der Unterschied zwischen TCP und UDP?",
          answer: "TCP (Transmission Control Protocol) ist verbindungsorientiert und gewährleistet die zuverlässige Übertragung, während UDP (User Datagram Protocol) verbindungslos ist und keine Garantie für die Zustellung bietet, aber dafür schneller ist."
        },
        {
          id: String(cards.length + 2),
          question: "Erklären Sie das Konzept von 'Big O' Notation.",
          answer: "Die Big O Notation beschreibt die Laufzeitkomplexität eines Algorithmus im schlimmsten Fall. Sie gibt an, wie sich die Laufzeit mit wachsender Eingabegröße verhält, z.B. O(n) für lineares Wachstum oder O(n²) für quadratisches Wachstum."
        }
      ];
      
      setCards(newCards);
      setIsGenerating(false);
    }, 2000);
  };
  
  // Wenn keine Karten vorhanden sind, zeige eine Meldung an
  if (cards.length === 0) {
    return (
      <div className="text-center py-12">
        <h3 className="text-xl font-medium">Keine Karteikarten verfügbar</h3>
        <p className="text-muted-foreground mt-2">
          Es wurden keine Karteikarten für diesen Inhalt generiert.
        </p>
      </div>
    );
  }
  
  return (
    <section className="py-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex flex-col md:flex-row gap-8 items-center">
          <div className="flex-1 w-full">
            <div className="relative mx-auto max-w-md perspective-1000">
              <div 
                className={`card-container relative w-full h-[320px] transition-transform duration-700 transform-style-3d ${
                  isFlipped ? 'rotate-y-180' : ''
                }`}
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
                      {cards[currentCardIndex]?.question}
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
                      {cards[currentCardIndex]?.answer}
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
              
              <div className="flex space-x-1">
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
          </div>
          
          <div className="w-full md:w-64 flex flex-col space-y-4">
            <Card className="border border-border/50 shadow-soft">
              <CardContent className="pt-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Gesamt</span>
                    <span className="text-sm">{cards.length} Karten</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Gelernt</span>
                    <span className="text-sm">{Math.floor(cards.length * 0.6)} Karten</span>
                  </div>
                  <div className="h-2 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full bg-primary rounded-full" style={{ width: '60%' }}></div>
                  </div>
                  
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
