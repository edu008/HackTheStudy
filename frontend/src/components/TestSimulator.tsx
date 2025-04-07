import { useState, useEffect } from 'react';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { useToast } from "@/components/ui/use-toast";
import { Question } from '@/types';

// Interface für intern verwendete Fragen
interface TestQuestion {
  id: string;
  text: string;
  options: string[];
  correctAnswer: number;
  explanation?: string;
}

// Beispielfragen für den Fall, dass keine Fragen übergeben werden
const sampleQuestions: TestQuestion[] = [
  {
    id: "1",
    text: "Welche Aussage zum Black-Box-Testing ist korrekt?",
    options: [
      "Der Tester hat vollen Zugriff auf den Quellcode.",
      "Der Tester kennt die internen Strukturen der Software.",
      "Der Tester betrachtet nur das Ein- und Ausgabeverhalten.",
      "Black-Box-Testing ist weniger effektiv als White-Box-Testing."
    ],
    correctAnswer: 2,
    explanation: "Beim Black-Box-Testing wird die Software als 'schwarze Box' betrachtet, bei der nur das externe Verhalten getestet wird, ohne Kenntnis der internen Struktur oder des Quellcodes."
  },
  {
    id: "2",
    text: "Was ist das Hauptziel der Normalformen in relationalen Datenbanken?",
    options: [
      "Maximierung der Datenspeichereffizienz",
      "Minimierung der Redundanz und der Anomalien",
      "Verbesserung der Abfragegeschwindigkeit",
      "Erhöhung der Komplexität der Datenbank"
    ],
    correctAnswer: 1,
    explanation: "Normalformen in relationalen Datenbanken dienen primär dazu, Datenredundanz zu reduzieren und Anomalien zu vermeiden, die bei Einfüge-, Aktualisierungs- oder Löschvorgängen auftreten können."
  },
  {
    id: "3",
    text: "Welcher Sortieralgorithmus hat die beste durchschnittliche Zeitkomplexität?",
    options: [
      "Bubble Sort",
      "Selection Sort",
      "Insertion Sort",
      "Quick Sort"
    ],
    correctAnswer: 3,
    explanation: "Quick Sort hat im Durchschnitt eine Zeitkomplexität von O(n log n), was besser ist als die O(n²) Komplexität von Bubble Sort, Selection Sort und Insertion Sort."
  }
];

// Funktion zum Konvertieren der API-Fragen in das interne Format
const convertQuestions = (apiQuestions: Question[]): TestQuestion[] => {
  return apiQuestions.map(q => {
    // Ermittle den Index der korrekten Antwort
    let correctAnswerIndex = 0;
    
    if (typeof q.correctAnswer === 'number') {
      // Wenn die Frage bereits einen numerischen correctAnswer-Wert hat
      correctAnswerIndex = q.correctAnswer;
    } else if (q.correct_answer) {
      // Ansonsten suche den Index der korrekten Antwort in den Optionen
      correctAnswerIndex = q.options.findIndex(opt => opt === q.correct_answer);
      // Fallback, falls nicht gefunden
      if (correctAnswerIndex === -1) correctAnswerIndex = 0;
    }
    
    return {
      id: q.id,
      text: q.text,
      options: q.options,
      correctAnswer: correctAnswerIndex,
      explanation: q.explanation
    };
  });
};

interface TestSimulatorProps {
  questions?: Question[];
}

const TestSimulator: React.FC<TestSimulatorProps> = ({ questions: apiQuestions }) => {
  const { toast } = useToast();
  const [questions, setQuestions] = useState<TestQuestion[]>([]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<string, number>>({});
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  
  // Konvertiere die übergebenen Fragen ins interne Format
  useEffect(() => {
    if (apiQuestions && apiQuestions.length > 0) {
      setQuestions(convertQuestions(apiQuestions));
    } else {
      setQuestions(sampleQuestions);
    }
    // Zurücksetzen des Zustands bei neuen Fragen
    setCurrentQuestionIndex(0);
    setSelectedAnswers({});
    setIsSubmitted(false);
  }, [apiQuestions]);
  
  // Sicherstellen, dass wir Fragen haben
  if (questions.length === 0) {
    return (
      <div className="text-center py-12">
        <h3 className="text-xl font-medium">Keine Testfragen verfügbar</h3>
        <p className="text-muted-foreground mt-2">
          Es wurden keine Testfragen für diesen Inhalt generiert.
        </p>
      </div>
    );
  }
  
  const currentQuestion = questions[currentQuestionIndex];
  
  const handleAnswerSelect = (value: string) => {
    setSelectedAnswers({
      ...selectedAnswers,
      [currentQuestion.id]: parseInt(value)
    });
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
    setIsGenerating(true);
    
    // Simulate generating new questions
    setTimeout(() => {
      const newQuestions = [
        ...questions,
        {
          id: questions.length + 1,
          text: "Welches Protokoll wird für die sichere Übertragung von Webseiten verwendet?",
          options: [
            "HTTP",
            "FTP",
            "HTTPS",
            "SMTP"
          ],
          correctAnswer: 2
        },
        {
          id: questions.length + 2,
          text: "Was ist ein Hauptvorteil von Dependency Injection?",
          options: [
            "Erhöhte Performanz",
            "Vereinfachte Testbarkeit",
            "Reduzierte Codezeilen",
            "Automatische Fehlerbehebung"
          ],
          correctAnswer: 1
        }
      ];
      
      setQuestions(newQuestions);
      setIsGenerating(false);
      setIsSubmitted(false);
      setSelectedAnswers({});
      
      toast({
        title: "Neue Fragen generiert",
        description: "Es wurden neue Fragen zu deinem Test hinzugefügt.",
      });
    }, 2000);
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
              
              {isSubmitted && currentQuestion.explanation && (
                <div className="mt-6 p-4 bg-secondary/50 rounded-lg">
                  <p className="font-medium">Erklärung:</p>
                  <p className="text-muted-foreground">
                    {currentQuestion.explanation}
                  </p>
                </div>
              )}
            </div>
          </CardContent>
          
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
                  Test wiederholen
                </Button>
              ) : (
                <Button 
                  onClick={currentQuestionIndex === questions.length - 1 ? handleSubmit : handleNext}
                  disabled={!selectedAnswers[currentQuestion.id] && currentQuestionIndex === questions.length - 1}
                >
                  {currentQuestionIndex === questions.length - 1 ? 'Abgeben' : 'Weiter'}
                </Button>
              )}
            </div>
          </CardFooter>
        </Card>
        
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
      </div>
    </section>
  );
};

export default TestSimulator;
