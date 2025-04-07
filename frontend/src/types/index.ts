/**
 * Zentrale Typdefinitionen für das Projekt
 */

/**
 * Benutzer-Typ
 */
export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  credits: number;
  created_at?: string;
  updated_at?: string;
}

/**
 * Auth-Antwort vom Server
 */
export interface AuthResponse {
  user: User;
  token: string;
  refreshToken: string;
}

/**
 * Thema (Topic)
 */
export interface Topic {
  id: string;
  name: string;
  description?: string;
  parent_id?: string;
  is_main_topic?: boolean;
  // Zusätzliche Felder für ConceptMapper
  text?: string;
  x?: number;
  y?: number;
}

/**
 * Lernkarte (Flashcard)
 */
export interface Flashcard {
  id: string;
  question: string;
  answer: string;
  topic_id?: string;
  difficulty?: string;
}

/**
 * Test-Frage (Question)
 */
export interface Question {
  id: string;
  text: string;
  options: string[];
  correct_answer: string;
  explanation?: string;
  // Optional für Kompatibilität mit TestSimulator
  correctAnswer?: number;
}

/**
 * Antwortmöglichkeit für Multiple-Choice-Fragen
 */
export interface QuestionOption {
  id: string;
  content: string;
  is_correct: boolean;
}

/**
 * Hochgeladenes Dokument (Upload)
 */
export interface Upload {
  id: string;
  session_id: string;
  user_id?: string;
  created_at: string;
  updated_at: string;
  last_used_at?: string;
  overall_processing_status?: string;
  error_message?: string;
  upload_metadata?: Record<string, any>;
  // Alte Felder (ggf. entfernen, wenn nicht mehr im Backend)
  file_name_1?: string;
  file_content_1?: string; // Normalerweise nicht im Frontend benötigt
}

/**
 * Typ für eine einzelne hochgeladene Datei (Info)
 */
export interface UploadedFileInfo {
  name: string;
  size: number;
  type: string;
}

/**
 * NEUER TYP: Antwort vom /upload/file Endpunkt
 */
export interface UploadApiResponse {
  success: boolean;
  message: string;
  session_id: string;
  upload_id: string;
  files: UploadedFileInfo[]; // Liste der verarbeiteten Datei-Infos
  task_ids: string[]; // Liste der gestarteten Task-IDs
  error?: { // Optional, falls Fehler auftritt
    code?: string;
    message?: string;
  };
}

/**
 * Zahlungs-Transaktion
 */
export interface Payment {
  id: string;
  amount: number;
  credits: number;
  status: 'pending' | 'completed' | 'failed';
  created_at?: string;
  updated_at?: string;
  user_id: string;
}

/**
 * Benutzerverlauf (History)
 */
export interface UserHistoryItem {
  id: string;
  action: 'upload' | 'flashcard_generate' | 'question_generate' | 'concept_map';
  description: string;
  entity_id?: string;
  entity_type?: string;
  created_at: string;
  user_id: string;
}

export interface TokenResponse {
  token: string;
  refreshToken: string;
}

export interface ApiError {
  message: string;
  code?: string;
  status?: number;
}

// Füge UploadResults-Typdefinition hinzu
export interface UploadResults {
  success: boolean;
  status: string;
  data?: {
    session_id: string;
    flashcards: Flashcard[];
    test_questions: Question[];
    analysis: {
      main_topic: string;
      subtopics: string[];
    };
    topics: {
      main_topic: {
        id: string;
        name: string;
      };
      subtopics: Topic[];
    };
    connections: {
      id: string;
      source_id: string;
      target_id: string;
      label: string;
    }[];
  };
  flashcards?: Flashcard[];
  test_questions?: Question[];
}

export interface TopicHierarchy {
  topics: Topic[];
  connections: any[]; // Ggf. genauer typisieren
} 