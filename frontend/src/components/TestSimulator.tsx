
import { useState, useEffect } from 'react';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { CheckCircle, XCircle, Loader2, AlertCircle } from 'lucide-react';
import { useToast } from "@/hooks/use-toast";

interface Question {
  id: number;
  text: string;
  options: string[];
  correctAnswer: number;
}

// Sample questions to show when no data is available
const sampleQuestions: Question[] = [
  {
    id: 1,
    text: "Welche Aussage zum Black-Box-Testing ist korrekt?",
    options: [
      "Der Tester hat vollen Zugriff auf den Quellcode.",
      "Der Tester kennt die internen Strukturen der Software.",
      "Der Tester betrachtet nur das Ein- und Ausgabeverhalten.",
      "Black-Box-Testing ist weniger effektiv als White-Box-Testing."
    ],
    correctAnswer: 2
  },
  {
    id: 2,
    text: "Was ist das Hauptziel der Normalformen in relationalen Datenbanken?",
    options: [
      "Maximierung der Datenspeichereffizienz",
      "Minimierung der Redundanz und der Anomalien",
      "Verbesserung der Abfragegeschwindigkeit",
      "Erhöhung der Komplexität der Datenbank"
    ],
    correctAnswer: 1
  },
  {
    id: 3,
    text: "Welcher Sortieralgorithmus hat die beste durchschnittliche Zeitkomplexität?",
    options: [
      "Bubble Sort",
      "Selection Sort",
      "Insertion Sort",
      "Quick Sort"
    ],
    correctAnswer: 3
  }
];

interface TestSimulatorProps {
  questions?: Question[];
  onGenerateMore?: () => void;
  isGenerating?: boolean;
}

const TestSimulator = ({
  questions: providedQuestions,
  onGenerateMore,
  isGenerating = false
}: TestSimulatorProps) => {
  const { toast } = useToast();
  const [questions, setQuestions] = useState<Question[]>(providedQuestions || sampleQuestions);
  
  // Update questions when props change
  useEffect(() => {
    if (providedQuestions && providedQuestions.length > 0) {
      setQuestions(providedQuestions);
      setCurrentQuestionIndex(0);
      setSelectedAnswers({});
      setIsSubmitted(false);
    }
  }, [providedQuestions]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, number>>({});
  const [isSubmitted, setIsSubmitted] = useState(false);
  
  // Make sure we have a valid current question
  const currentQuestion = questions.length > 0 ? questions[currentQuestionIndex] : null;
  
  const handleAnswerSelect = (value: string) => {
    if (currentQuestion) {
      setSelectedAnswers({
        ...selectedAnswers,
        [currentQuestion.id]: parseInt(value)
      });
    }
  };
  
  const handleNext = () => {
    if (currentQuestionIndex < questions.length - 1) {
      setCurrentQuestionIndex(prevIndex => prevIndex + 1);
    }
  };
  
  const handlePrevious = () => {
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex(prevIndex => prevIndex - 1);
    }
  };
  
  const handleSubmit = () => {
    // Check if all questions are answered
    if (Object.keys(selectedAnswers).length < questions.length) {
      toast({
        title: "Nicht alle Fragen beantwortet",
        description: "Bitte beantworte alle Fragen bevor du abgibst.",
        variant: "destructive",
      });
      return;
    }
    
    setIsSubmitted(true);
    
    // Calculate score
    const correctAnswers = questions.filter(
      q => selectedAnswers[q.id] === q.correctAnswer
    ).length;
    
    toast({
      title: "Test abgeschlossen",
      description: `Du hast ${correctAnswers} von ${questions.length} Fragen richtig beantwortet.`,
    });
  };
  
  const handleGenerateMore = () => {
    if (onGenerateMore) {
      onGenerateMore();
    }
  };
  
  const resetTest = () => {
    setIsSubmitted(false);
    setSelectedAnswers({});
    setCurrentQuestionIndex(0);
  };
  
  return (
    <section id="simulator" className="section-container">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12 space-y-4">
          <h2 className="text-3xl md:text-4xl font-bold animate-fade-in">
            Test-Simulation
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto animate-fade-in">
            Bereite dich mit KI-generierten Testfragen optimal auf deine Prüfung vor.
          </p>
        </div>
        
        <Card className="border border-border/50 shadow-soft overflow-hidden animate-slide-up">
          <CardHeader className="pb-4 border-b bg-secondary/30">
            <div className="flex justify-between items-center">
              <CardTitle>Prüfungssimulation</CardTitle>
              <div className="text-sm text-muted-foreground">
                Frage {currentQuestionIndex + 1} von {questions.length}
              </div>
            </div>
          </CardHeader>
          
          <CardContent className="p-6">
            {currentQuestion ? (
              <div className="space-y-6">
                <div>
                  <h3 className="text-xl font-medium mb-6">{currentQuestion.text}</h3>
                  
                  <RadioGroup
                    value={selectedAnswers[currentQuestion.id]?.toString()}
                    onValueChange={handleAnswerSelect}
                    className="space-y-4"
                    disabled={isSubmitted}
                  >
                    {currentQuestion.options.map((option, index) => (
                    <div 
                      key={index} 
                      className={`flex items-start space-x-3 p-3 rounded-lg border transition-all ${
                        isSubmitted && selectedAnswers[currentQuestion.id] === index && currentQuestion.correctAnswer === index
                          ? 'border-green-500 bg-green-50 dark:bg-green-950/20'
                          : isSubmitted && selectedAnswers[currentQuestion.id] === index
                            ? 'border-red-500 bg-red-50 dark:bg-red-950/20'
                            : isSubmitted && currentQuestion.correctAnswer === index
                              ? 'border-green-500/50 bg-green-50/50 dark:bg-green-950/10'
                              : selectedAnswers[currentQuestion.id] === index
                                ? 'border-primary bg-primary/5' 
                                : 'border-border hover:border-primary/30 hover:bg-secondary/50'
                      }`}
                    >
                      <RadioGroupItem 
                        value={index.toString()} 
                        id={`option-${index}`} 
                        className="mt-1"
                      />
                      <div className="flex-1 flex justify-between">
                        <Label 
                          htmlFor={`option-${index}`}
                          className="cursor-pointer"
                        >
                          {option}
                        </Label>
                        
                        {isSubmitted && (
                          <div className="flex items-center">
                            {currentQuestion.correctAnswer === index ? (
                              <CheckCircle className="h-5 w-5 text-green-500" />
                            ) : selectedAnswers[currentQuestion.id] === index ? (
                              <XCircle className="h-5 w-5 text-red-500" />
                            ) : null}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  </RadioGroup>
                </div>
                
                {isSubmitted && (
                  <div className="mt-6 p-4 bg-secondary/50 rounded-lg">
                    <p className="font-medium">Erklärung:</p>
                    <p className="text-muted-foreground">
                      {currentQuestion.correctAnswer === 2 && currentQuestion.id === 1 && 
                        "Beim Black-Box-Testing wird die Software als 'schwarze Box' betrachtet, bei der nur das externe Verhalten getestet wird, ohne Kenntnis der internen Struktur oder des Quellcodes."}
                      {currentQuestion.correctAnswer === 1 && currentQuestion.id === 2 && 
                        "Normalformen in relationalen Datenbanken dienen primär dazu, Datenredundanz zu reduzieren und Anomalien zu vermeiden, die bei Einfüge-, Aktualisierungs- oder Löschvorgängen auftreten können."}
                      {currentQuestion.correctAnswer === 3 && currentQuestion.id === 3 && 
                        "Quick Sort hat im Durchschnitt eine Zeitkomplexität von O(n log n), was besser ist als die O(n²) Komplexität von Bubble Sort, Selection Sort und Insertion Sort."}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-8 text-center">
                <AlertCircle className="h-12 w-12 text-amber-500 mx-auto mb-4" />
                <h3 className="text-xl font-medium mb-2">Keine Testfragen verfügbar</h3>
                <p className="text-muted-foreground">
                  Lade zuerst eine Prüfung hoch, um Testfragen zu generieren.
                </p>
              </div>
            )}
          </CardContent>
          
          {currentQuestion && (
            <CardFooter className="flex justify-between border-t bg-secondary/30 pt-4">
              <div>
                <Button 
                  variant="outline" 
                  onClick={handlePrevious}
                  disabled={currentQuestionIndex === 0}
                >
                  Zurück
                </Button>
              </div>
              
              <div>
                {isSubmitted ? (
                  <Button onClick={resetTest}>
                    Test zurücksetzen
                  </Button>
                ) : currentQuestionIndex === questions.length - 1 ? (
                  <Button onClick={handleSubmit}>
                    Abgeben
                  </Button>
                ) : (
                  <Button onClick={handleNext}>
                    Weiter
                  </Button>
                )}
              </div>
            </CardFooter>
          )}
        </Card>
        
        {questions.length > 0 ? (
          <div className="mt-8 flex justify-center">
            <Button 
              variant="outline" 
              onClick={handleGenerateMore}
              disabled={isGenerating}
              className="gap-2"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generiere neue Fragen...
                </>
              ) : (
                <>
                  Mehr Testfragen generieren
                </>
              )}
            </Button>
          </div>
        ) : (
          <div className="mt-8 p-6 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg max-w-md mx-auto">
            <div className="flex items-center gap-3 mb-2">
              <AlertCircle className="h-5 w-5 text-amber-500" />
              <h3 className="font-medium text-amber-700 dark:text-amber-400">Keine Testfragen verfügbar</h3>
            </div>
            <p className="text-amber-600 dark:text-amber-300">
              Lade zuerst eine Prüfung hoch, um Testfragen zu generieren.
            </p>
          </div>
        )}
      </div>
    </section>
  );
};

export default TestSimulator;
