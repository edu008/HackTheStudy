import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { CheckCircle, XCircle, Loader2, AlertCircle, Coins, RefreshCw, Check, X } from 'lucide-react';
import { useToast } from "@/hooks/use-toast";
import { useTranslation } from 'react-i18next';

interface Question {
  id?: string;
  text: string;
  options: string[];
  correctAnswer?: number;
  correct?: number;
  explanation?: string;
}

interface TokenInfo {
  inputTokens: number;
  outputTokens: number;
  cost: number;
}

interface TestSimulatorProps {
  questions?: Question[];
  onGenerateMore?: () => void;
  isGenerating?: boolean;
  tokenInfo?: TokenInfo;
}

const TestSimulator = ({
  questions: providedQuestions = [],
  onGenerateMore,
  isGenerating = false,
  tokenInfo
}: TestSimulatorProps) => {
  const { toast } = useToast();
  const { t } = useTranslation();
  
  // Main state
  const [processedQuestions, setProcessedQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answeredQuestions, setAnsweredQuestions] = useState<Record<string, number>>({});
  const [selectedOption, setSelectedOption] = useState<string | undefined>(undefined);
  const [previousQuestionsLength, setPreviousQuestionsLength] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [totalQuestions, setTotalQuestions] = useState(0);
  const [score, setScore] = useState({ correct: 0, total: 0 });
  
  // Current question
  const currentQuestion = processedQuestions[currentIndex] || null;
  
  // Vollständig initial laden
  useEffect(() => {
    // Beim ersten Laden einen längeren Ladebildschirm zeigen
    setIsLoading(true);
    
    // Verzögertes setzen der Fragen, um sicherzustellen, dass
    // wir nie die falschen Werte anzeigen
    const timer = setTimeout(() => {
      // Reset wenn keine Fragen vorhanden sind
      if (providedQuestions.length === 0) {
        setProcessedQuestions([]);
        setCurrentIndex(0);
        setAnsweredQuestions({});
        setSelectedOption(undefined);
        setPreviousQuestionsLength(0);
        setTotalQuestions(0); // Explizit auf 0 setzen
        setIsLoading(false);
        return;
      }
      
      // Wenn Fragen vorhanden sind, verarbeite diese
      const processedQuestions = providedQuestions.map(q => ({
        ...q,
        correct: undefined
      }));
      
      // Prüfe, ob neue Fragen hinzugefügt wurden
      if (previousQuestionsLength > 0 && providedQuestions.length > previousQuestionsLength) {
        // Neue Fragen wurden hinzugefügt, setze den Index auf die erste neue Frage
        setProcessedQuestions(processedQuestions);
        setCurrentIndex(previousQuestionsLength);
        
        console.log(`Neue Testfragen erkannt: ${previousQuestionsLength} -> ${providedQuestions.length}`);
      } else {
        // Initiale Ladung oder vollständiger Ersatz, aber behalte den aktuellen Index, wenn möglich
        setProcessedQuestions(processedQuestions);
        
        // Wenn es bereits Fragen gab und der aktuelle Index noch gültig ist
        if (previousQuestionsLength > 0 && currentIndex < processedQuestions.length) {
          // Index beibehalten
        } else {
          // Zurück zur ersten Frage
          setCurrentIndex(0);
        }
      }
      
      // Aktualisiere die Länge für den nächsten Vergleich
      setPreviousQuestionsLength(providedQuestions.length);
      
      // Verzögertes Setzen der totalQuestions NACH allen anderen Updates
      setTimeout(() => {
        // Setze totalQuestions explizit auf die Länge der providedQuestions
        setTotalQuestions(providedQuestions.length);
        
        // Zum Schluss loading auf false setzen
        setIsLoading(false);
        
        // Nach dem Laden zu den Fragen scrollen, falls neue hinzugefügt wurden
        if (previousQuestionsLength > 0 && providedQuestions.length > previousQuestionsLength) {
          setTimeout(() => {
            document.getElementById('simulator')?.scrollIntoView({ behavior: 'smooth' });
          }, 100);
        }
      }, 200); // Extra Verzögerung für die totalQuestions
      
    }, 500); // Erhöhte Verzögerung, um sicherzustellen, dass alle Daten verarbeitet sind
    
    return () => clearTimeout(timer);
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
    if (currentIndex < totalQuestions - 1) {
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
    <section className="py-14 md:py-20 bg-slate-50">
      <div className="container mx-auto max-w-5xl">
        <div className="text-center mb-12 space-y-4">
          <h2 className="text-3xl md:text-4xl font-bold">
            {t('tests.title')}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t('tests.description')}
          </p>
        </div>
        
        <Card className="border border-border/50 shadow-soft mb-4">
          <CardHeader className="bg-secondary/30">
            <CardTitle className="flex justify-between items-center">
              {processedQuestions.length > 0 ? (
                <div className="flex items-center">
                  <span>{t('tests.question')} {currentIndex + 1}/{totalQuestions}</span>
                </div>
              ) : (
                <span>{t('tests.title')}</span>
              )}
              
              {processedQuestions.length > 0 && (
                <div className="text-base">
                  {score.total > 0 ? (
                    <span className="text-muted-foreground">
                      {t('tests.score')}: <span className="font-semibold">{score.correct}/{score.total}</span>
                    </span>
                  ) : null}
                </div>
              )}
            </CardTitle>
            {processedQuestions.length > 0 && (
              <CardDescription>
                {t('tests.selectAnswer')}
              </CardDescription>
            )}
          </CardHeader>

          <CardContent className="p-6">
            {currentQuestion ? (
              <div className="space-y-6">
                <div className="text-xl font-medium">{currentQuestion.text}</div>
                
                <div className="space-y-3">
                  {currentQuestion.options.map((option, index) => (
                    <div 
                      key={index}
                      className={`p-4 rounded-lg border cursor-pointer transition-all ${
                        selectedOption === index 
                          ? 'border-primary bg-primary/5' 
                          : 'border-border hover:border-primary/40 hover:bg-secondary/50'
                      } ${
                        isCurrentQuestionAnswered && index === getCorrectAnswerIndex(currentQuestion)
                          ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                          : isCurrentQuestionAnswered && selectedOption === index && index !== getCorrectAnswerIndex(currentQuestion)
                          ? 'border-red-500 bg-red-50 dark:bg-red-900/20'
                          : ''
                      }`}
                      onClick={() => !isCurrentQuestionAnswered && handleAnswerSelect(index.toString())}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`flex items-center justify-center h-6 w-6 rounded-full shrink-0 text-sm ${
                          selectedOption === index ? 'bg-primary text-white' : 'bg-muted text-muted-foreground'
                        } ${
                          isCurrentQuestionAnswered && index === getCorrectAnswerIndex(currentQuestion)
                            ? 'bg-green-500 text-white'
                            : isCurrentQuestionAnswered && selectedOption === index && index !== getCorrectAnswerIndex(currentQuestion)
                            ? 'bg-red-500 text-white'
                            : ''
                        }`}>
                          {isCurrentQuestionAnswered && index === getCorrectAnswerIndex(currentQuestion) ? (
                            <Check className="h-3 w-3" />
                          ) : isCurrentQuestionAnswered && selectedOption === index && index !== getCorrectAnswerIndex(currentQuestion) ? (
                            <X className="h-3 w-3" />
                          ) : (
                            String.fromCharCode(65 + index)
                          )}
                        </div>
                        <div>{option}</div>
                      </div>
                    </div>
                  ))}
                </div>
                
                {isCurrentQuestionAnswered && currentQuestion.explanation && (
                  <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-800">
                    <div className="font-medium text-blue-800 dark:text-blue-300 mb-1">
                      {t('tests.explanation')}:
                    </div>
                    <div className="text-blue-800 dark:text-blue-300">
                      {currentQuestion.explanation}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-12 text-center">
                <h3 className="text-xl font-semibold mb-2">
                  {t('tests.noQuestionsAvailable')}
                </h3>
                <p className="text-muted-foreground">
                  {t('tests.uploadFirst')}
                </p>
              </div>
            )}
          </CardContent>

          {currentQuestion ? (
            <CardFooter className="flex justify-between items-center border-t bg-secondary/30 pt-4">
              <div className="flex space-x-2">
                <Button
                  variant="outline"
                  onClick={handlePrevious}
                  disabled={currentIndex === 0}
                >
                  {t('tests.previous')}
                </Button>
                <Button
                  variant="outline"
                  onClick={handleNext}
                  disabled={currentIndex === totalQuestions - 1}
                >
                  {t('tests.next')}
                </Button>
              </div>
              
              <div className="flex space-x-2">
                {!isCurrentQuestionAnswered && (
                  <Button 
                    onClick={handleSubmit}
                    disabled={selectedOption === undefined}
                  >
                    {t('tests.checkAnswer')}
                  </Button>
                )}
                
                <Button 
                  onClick={handleGenerateMore}
                  disabled={isGenerating}
                  variant="outline"
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {t('tests.generating')}
                    </>
                  ) : (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      {t('tests.moreQuestions')}
                    </>
                  )}
                </Button>
              </div>
            </CardFooter>
          ) : (
            <CardFooter className="bg-secondary/30 pt-4">
              <Button 
                onClick={handleGenerateMore}
                disabled={isGenerating}
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {t('tests.generatingQuestions')}
                  </>
                ) : (
                  t('tests.generateQuestions')
                )}
              </Button>
            </CardFooter>
          )}
        </Card>
        
        {tokenInfo && (
          <div className="mt-4 p-4 bg-white dark:bg-gray-950 rounded-lg border border-border/50 shadow-soft">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <Coins className="h-4 w-4 text-amber-500" />
                <span className="text-sm font-medium">{t('tests.tokenUsage')}</span>
              </div>
              <span className="text-sm font-medium text-amber-600">{tokenInfo.cost} Credits</span>
            </div>
            <div className="grid grid-cols-2 text-sm">
              <span className="text-muted-foreground">{t('tests.input')}:</span>
              <span className="text-right">{tokenInfo.inputTokens}</span>
              <span className="text-muted-foreground">{t('tests.output')}:</span>
              <span className="text-right">{tokenInfo.outputTokens}</span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
};

export default TestSimulator;
