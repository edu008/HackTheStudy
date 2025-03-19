import { useState, useEffect } from 'react';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { CheckCircle, XCircle, Loader2, AlertCircle } from 'lucide-react';
import { useToast } from "@/hooks/use-toast";

interface Question {
  id?: string;
  text: string;
  options: string[];
  correctAnswer?: number;
  correct?: number;
  explanation?: string;
}

interface TestSimulatorProps {
  questions?: Question[];
  onGenerateMore?: () => void;
  isGenerating?: boolean;
}

const TestSimulator = ({
  questions: providedQuestions = [],
  onGenerateMore,
  isGenerating = false
}: TestSimulatorProps) => {
  const { toast } = useToast();
  
  // Main state
  const [processedQuestions, setProcessedQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answeredQuestions, setAnsweredQuestions] = useState<Record<string, number>>({});
  const [selectedOption, setSelectedOption] = useState<string | undefined>(undefined);
  
  // Current question
  const currentQuestion = processedQuestions[currentIndex] || null;
  
  // Process provided questions when they change
  useEffect(() => {
    // Reset wenn keine Fragen vorhanden sind
    if (providedQuestions.length === 0) {
      setProcessedQuestions([]);
      setCurrentIndex(0);
      setAnsweredQuestions({});
      setSelectedOption(undefined);
      return;
    }
    
    // Wenn Fragen vorhanden sind, verarbeite diese
    const processedQuestions = providedQuestions.map(q => ({
      ...q,
      correct: undefined
    }));
    
    setProcessedQuestions(processedQuestions);
    
    // Create a new object with question IDs as keys
    const questionsWithIds = processedQuestions.reduce((acc, curr) => {
      acc[curr.id] = curr;
      return acc;
    }, {});
  }, [providedQuestions]);
  
  // Reset selected option when changing questions
  useEffect(() => {
    const isAnswered = currentQuestion && answeredQuestions[currentQuestion.id!] !== undefined;
    if (isAnswered) {
      setSelectedOption(answeredQuestions[currentQuestion.id!].toString());
    } else {
      setSelectedOption(undefined);
    }
  }, [currentIndex, currentQuestion, answeredQuestions]);
  
  // Get the correct answer index for a question
  const getCorrectAnswerIndex = (question: Question): number => {
    if (!question) return 0;
    return question.correctAnswer !== undefined ? question.correctAnswer : 
           question.correct !== undefined ? question.correct : 0;
  };
  
  // Handle option selection
  const handleAnswerSelect = (value: string) => {
    setSelectedOption(value);
  };
  
  // Navigate to next question
  const handleNext = () => {
    if (currentIndex < processedQuestions.length - 1) {
      setCurrentIndex(currentIndex + 1);
    }
  };
  
  // Navigate to previous question
  const handlePrevious = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };
  
  // Submit answer
  const handleSubmit = () => {
    if (!currentQuestion || selectedOption === undefined) {
      toast({
        title: "Keine Antwort ausgewählt",
        description: "Bitte wähle eine Antwort aus, um fortzufahren.",
        variant: "destructive",
      });
      return;
    }
    
    const selectedValue = parseInt(selectedOption);
    
    // Record the answer
    setAnsweredQuestions(prev => ({
      ...prev,
      [currentQuestion.id!]: selectedValue
    }));
  };
  
  // Generate more questions
  const handleGenerateMore = () => {
    if (onGenerateMore) {
      onGenerateMore();
    }
  };
  
  // Reset the test
  const resetTest = () => {
    setAnsweredQuestions({});
    setSelectedOption(undefined);
    setCurrentIndex(0);
  };
  
  // Check if current question is answered
  const isCurrentQuestionAnswered = currentQuestion && 
                                   answeredQuestions[currentQuestion.id!] !== undefined;
  
  return (
    <section id="simulator" className="section-container">
      <div className="max-w-4xl mx-auto">
        <Card className="border border-border/50 shadow-soft overflow-hidden animate-slide-up">
          <CardHeader className="pb-4 border-b bg-secondary/30">
            <div className="flex justify-between items-center">
              <CardTitle>Prüfungssimulation</CardTitle>
              <div className="text-sm text-muted-foreground">
                Frage {currentIndex + 1} von {processedQuestions.length}
                {processedQuestions.length > 0 && (
                  <span className="ml-2 text-xs">
                  </span>
                )}
              </div>
            </div>
          </CardHeader>

          <CardContent className="p-6">
            {currentQuestion ? (
              <div className="space-y-6">
                <h3 className="text-xl font-medium mb-6">{currentQuestion.text.replace(/\*\*/g, '')}</h3>
                
                <RadioGroup
                  key={`question-${currentQuestion.id}-${isCurrentQuestionAnswered}`}
                  value={selectedOption}
                  onValueChange={handleAnswerSelect}
                  className="space-y-4"
                  disabled={isCurrentQuestionAnswered}
                >
                  {currentQuestion.options.map((option, index) => {
                    const optionId = `question-${currentQuestion.id}-option-${index}`;
                    const isSelected = isCurrentQuestionAnswered && 
                                      answeredQuestions[currentQuestion.id!] === index;
                    const correctAnswerIndex = getCorrectAnswerIndex(currentQuestion);
                    const isCorrect = correctAnswerIndex === index;
                    
                    let optionClass = "flex items-start space-x-3 p-3 rounded-lg border transition-all ";
                    
                    if (isCurrentQuestionAnswered) {
                      if (isSelected && isCorrect) {
                        optionClass += "border-green-500 bg-green-50 dark:bg-green-950/20";
                      } else if (isSelected) {
                        optionClass += "border-red-500 bg-red-50 dark:bg-red-950/20";
                      } else if (isCorrect) {
                        optionClass += "border-green-500/50 bg-green-50/50 dark:bg-green-950/10";
                      } else {
                        optionClass += "border-border";
                      }
                    } else {
                      optionClass += "border-border hover:border-primary/30 hover:bg-secondary/50";
                    }
                    
                    return (
                      <div key={optionId} className={optionClass}>
                        <RadioGroupItem
                          value={index.toString()}
                          id={optionId}
                          className="mt-1"
                        />
                        <div className="flex-1 flex justify-between">
                          <Label
                            htmlFor={optionId}
                            className="cursor-pointer"
                          >
                            {option.replace(/\*\*/g, '')}
                          </Label>
                          {isCurrentQuestionAnswered && (
                            <div className="flex items-center">
                              {isCorrect ? (
                                <CheckCircle className="h-5 w-5 text-green-500" />
                              ) : isSelected ? (
                                <XCircle className="h-5 w-5 text-red-500" />
                              ) : null}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </RadioGroup>
                
                {isCurrentQuestionAnswered && (
                  <div className="mt-6 p-4 bg-secondary/50 rounded-lg">
                    <p className="font-medium">Erklärung:</p>
                    <p className="text-muted-foreground">
                      {currentQuestion.explanation || 
                       `Die richtige Antwort ist ${currentQuestion.options[getCorrectAnswerIndex(currentQuestion)].replace(/\*\*/g, '')}.`}
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
              <Button
                variant="outline"
                onClick={handlePrevious}
                disabled={currentIndex === 0}
              >
                Zurück
              </Button>
              
              {isCurrentQuestionAnswered ? (
                currentIndex === processedQuestions.length - 1 ? (
                  <Button onClick={resetTest}>Test zurücksetzen</Button>
                ) : (
                  <Button onClick={handleNext}>Weiter zur nächsten Frage</Button>
                )
              ) : (
                <Button
                  onClick={handleSubmit}
                  disabled={selectedOption === undefined}
                >
                  Antwort prüfen
                </Button>
              )}
            </CardFooter>
          )}
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
              <>Mehr Testfragen generieren</>
            )}
          </Button>
        </div>
      </div>
    </section>
  );
};

export default TestSimulator;
