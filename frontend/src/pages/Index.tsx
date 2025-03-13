import { useState } from "react";
import Navbar from "@/components/Navbar";
import ExamUploader from "@/components/ExamUploader";
import FlashcardGenerator from "@/components/FlashcardGenerator";
import TestSimulator from "@/components/TestSimulator";
import Footer from "@/components/Footer";
import { useMutation } from "@tanstack/react-query";
import axios from "axios";
import { useToast } from "@/hooks/use-toast";

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

console.log('API_URL:', API_URL);

interface Flashcard {
  id: number;
  question: string;
  answer: string;
}

interface Question {
  id: number;
  text: string;
  options: string[];
  correctAnswer: number;
  explanation?: string;  // Make explanation optional to support both old and new questions
}

interface UploadResponse {
  success: boolean;
  message: string;
  flashcards: Flashcard[];
  questions: Question[];
}

const Index = () => {
  const { toast } = useToast();
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  
  const handleUploadSuccess = (data: UploadResponse) => {
    console.log('DEBUG: Index received upload success data:', data);
    console.log('DEBUG: Flashcards:', data.flashcards);
    console.log('DEBUG: Questions:', data.questions);
    setFlashcards(data.flashcards);
    setQuestions(data.questions);
    document.getElementById('flashcards')?.scrollIntoView({ behavior: 'smooth' });
  };
  
  const generateMoreFlashcardsMutation = useMutation({
    mutationFn: async () => {
      console.log('DEBUG: Requesting more flashcards from backend');
      const response = await axios.post<UploadResponse>(
        `${API_URL}/api/generate-more-flashcards`, 
        {},
        { withCredentials: true }
      );
      console.log('DEBUG: Received more flashcards response:', response.data);
      return response.data;
    },
    onSuccess: (data) => {
      setFlashcards(prevFlashcards => [...prevFlashcards, ...data.flashcards]);
      toast({
        title: "Neue Karteikarten generiert",
        description: `${data.flashcards.length} neue Karteikarten wurden erstellt.`,
      });
    },
    onError: () => {
      toast({
        title: "Fehler",
        description: "Beim Generieren neuer Karteikarten ist ein Fehler aufgetreten.",
        variant: "destructive",
      });
    }
  });
  
  const generateMoreQuestionsMutation = useMutation({
    mutationFn: async () => {
      console.log('DEBUG: Requesting more test questions from backend');
      const response = await axios.post<UploadResponse>(
        `${API_URL}/api/generate-more-questions`, 
        {},
        { withCredentials: true }
      );
      console.log('DEBUG: Received more test questions response:', response.data);
      return response.data;
    },
    onSuccess: (data) => {
      setQuestions(prevQuestions => [...prevQuestions, ...data.questions]);
      toast({
        title: "Neue Testfragen generiert",
        description: `${data.questions.length} neue Testfragen wurden erstellt.`,
      });
    },
    onError: () => {
      toast({
        title: "Fehler",
        description: "Beim Generieren neuer Testfragen ist ein Fehler aufgetreten.",
        variant: "destructive",
      });
    }
  });
  
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar onUploadSuccess={handleUploadSuccess} />
      <main className="flex-1">
        <section id="exam-uploader">
          <ExamUploader onUploadSuccess={handleUploadSuccess} />
        </section>
        <section id="flashcards">
          <FlashcardGenerator 
            flashcards={flashcards} 
            onGenerateMore={() => generateMoreFlashcardsMutation.mutate()}
            isGenerating={generateMoreFlashcardsMutation.isPending}
          />
        </section>
        <section id="test-simulator">
          <TestSimulator 
            questions={questions}
            onGenerateMore={() => generateMoreQuestionsMutation.mutate()}
            isGenerating={generateMoreQuestionsMutation.isPending}
          />
        </section>
      </main>
      <Footer />
    </div>
  );
};

export default Index;
