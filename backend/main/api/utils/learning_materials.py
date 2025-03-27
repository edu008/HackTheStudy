# api/learning_materials.py
"""
Funktionen zur Generierung von Lernmaterialien wie Flashcards und Fragen.
"""

import json
import logging
import re
from .ai_utils import query_chatgpt
from .text_processing import detect_language

logger = logging.getLogger(__name__)

def generate_additional_flashcards(text, client, analysis, existing_flashcards=None, num_to_generate=5, language='en', session_id=None, function_name="generate_additional_flashcards"):
    """
    Generiert zusätzliche Flashcards basierend auf dem Text und der Analyse.
    
    Args:
        text: Der Quelltext
        client: Der OpenAI-Client
        analysis: Die Analyse des Textes
        existing_flashcards: Bereits vorhandene Flashcards, um Duplikate zu vermeiden
        num_to_generate: Anzahl der zu generierenden Flashcards
        language: Die Sprache des Textes ('en' oder 'de')
        session_id: Session-ID für Tracking
        function_name: Name der Funktion für Logs
        
    Returns:
        list: Liste von Flashcard-Objekten
    """
    try:
        # Verwende eine Liste für vorhandene Flashcards, auch wenn None
        existing_fc = existing_flashcards or []
        
        # Extrahiere Themen aus der Analyse
        main_topic = analysis.get('main_topic', 'Allgemeines Thema')
        subtopics = analysis.get('subtopics', [])
        
        # Erstelle eine Liste der bereits vorhandenen Flashcard-Inhalte (Vorderseiten)
        existing_fronts = [fc.get('front', '') for fc in existing_fc]
        
        # System-Prompt basierend auf der Sprache
        if language == 'de':
            system_content = """Du bist ein KI-Assistent, der beim Erstellen von Lernkarten (Flashcards) hilft. 
            Deine Aufgabe ist es, effektive Frage-Antwort-Paare zu erstellen, die wichtige Konzepte, 
            Definitionen und Fakten abdecken."""
            
            user_prompt = f"""Erstelle {num_to_generate} Lernkarten basierend auf dem folgenden Text. 
            Das Hauptthema ist "{main_topic}".
            
            Relevant sind folgende Themen:
            {', '.join(subtopics[:5]) if subtopics else main_topic}
            
            Folgende Lernkarten existieren bereits (erstelle keine Duplikate):
            {' | '.join(existing_fronts[:10]) if existing_fronts else "Keine"}
            
            Erstelle Lernkarten, die folgende Kriterien erfüllen:
            1. Kurze, klare Frage oder Konzept auf der Vorderseite
            2. Präzise, informative Antwort auf der Rückseite
            3. Decke verschiedene Aspekte des Themas ab
            4. Sei präzise und achte auf Fachbegriffe
            
            Gib deine Antwort als JSON-Array zurück. Jede Lernkarte sollte diese Felder haben:
            - front: Der Text auf der Vorderseite
            - back: Der Text auf der Rückseite
            - difficulty: Die Schwierigkeit (easy, medium, hard)
            - topic: Das zugehörige Thema
            
            Hier ist der Text:
            {text[:5000]}"""
        else:
            system_content = """You are an AI assistant helping with creating flashcards. 
            Your task is to create effective question-answer pairs that cover important concepts, 
            definitions, and facts."""
            
            user_prompt = f"""Create {num_to_generate} flashcards based on the following text. 
            The main topic is "{main_topic}".
            
            Relevant topics include:
            {', '.join(subtopics[:5]) if subtopics else main_topic}
            
            The following flashcards already exist (don't create duplicates):
            {' | '.join(existing_fronts[:10]) if existing_fronts else "None"}
            
            Create flashcards that meet these criteria:
            1. Short, clear question or concept on the front
            2. Precise, informative answer on the back
            3. Cover different aspects of the topic
            4. Be precise and pay attention to technical terms
            
            Return your answer as a JSON array. Each flashcard should have these fields:
            - front: The text on the front
            - back: The text on the back
            - difficulty: The difficulty level (easy, medium, hard)
            - topic: The related topic
            
            Here's the text:
            {text[:5000]}"""
            
        # Sende die Anfrage an die KI
        response = query_chatgpt(
            prompt=user_prompt,
            client=client,
            system_content=system_content,
            temperature=0.7,
            use_cache=True,
            session_id=session_id,
            function_name=function_name
        )
        
        # Versuche, das JSON zu parsen
        try:
            # Entferne mögliche Markdown-Code-Blöcke
            json_text = re.sub(r'```json\s*|\s*```', '', response)
            flashcards = json.loads(json_text)
            
            # Stelle sicher, dass das Ergebnis eine Liste ist
            if isinstance(flashcards, dict) and 'flashcards' in flashcards:
                flashcards = flashcards['flashcards']
            elif not isinstance(flashcards, list):
                flashcards = [flashcards]
                
            # Validiere die Flashcards
            valid_flashcards = []
            for fc in flashcards:
                if isinstance(fc, dict) and 'front' in fc and 'back' in fc:
                    # Stelle sicher, dass alle erforderlichen Felder vorhanden sind
                    valid_fc = {
                        'front': fc.get('front', ''),
                        'back': fc.get('back', ''),
                        'difficulty': fc.get('difficulty', 'medium'),
                        'topic': fc.get('topic', main_topic)
                    }
                    valid_flashcards.append(valid_fc)
                    
            return valid_flashcards
        except Exception as e:
            logger.error(f"Fehler beim Parsen der Flashcards: {str(e)}")
            logger.debug(f"AI-Antwort war: {response}")
            
            # Versuche, die Antwort manuell zu parsen
            try:
                # Suche nach Muster wie "1. Front: ..., Back: ..." oder "Front: ...\nBack: ..."
                fc_pattern = r'(?:Front:|Vorderseite:)\s*([^\n]+)(?:[\n,]\s*(?:Back:|Rückseite:)\s*([^\n]+))'
                matches = re.findall(fc_pattern, response, re.IGNORECASE)
                
                if matches:
                    return [
                        {
                            'front': front.strip(),
                            'back': back.strip(),
                            'difficulty': 'medium',
                            'topic': main_topic
                        }
                        for front, back in matches[:num_to_generate]
                    ]
            except Exception as e2:
                logger.error(f"Alternativer Parsing-Versuch fehlgeschlagen: {str(e2)}")
            
            # Fallback: Generiere einfache Standardkarten
            return [
                {
                    'front': f"Was ist {main_topic}?" if language == 'de' else f"What is {main_topic}?",
                    'back': "Konnte keine Antwort generieren" if language == 'de' else "Could not generate answer",
                    'difficulty': 'medium',
                    'topic': main_topic
                }
            ]
    except Exception as e:
        logger.error(f"Fehler bei der Generierung von Flashcards: {str(e)}")
        
        # Generiere eine Standard-Flashcard
        default_front = f"Was ist {main_topic}?" if language == 'de' else f"What is {main_topic}?"
        default_back = "Fehler bei der Generierung" if language == 'de' else "Error during generation"
        
        return [{
            'front': default_front,
            'back': default_back,
            'difficulty': 'medium',
            'topic': main_topic
        }]

def generate_additional_questions(text, client, analysis, existing_questions=None, num_to_generate=3, language='en', session_id=None, function_name="generate_additional_questions"):
    """
    Generiert zusätzliche Fragen basierend auf dem Text und der Analyse.
    
    Args:
        text: Der Quelltext
        client: Der OpenAI-Client
        analysis: Die Analyse des Textes
        existing_questions: Bereits vorhandene Fragen, um Duplikate zu vermeiden
        num_to_generate: Anzahl der zu generierenden Fragen
        language: Die Sprache des Textes ('en' oder 'de')
        session_id: Session-ID für Tracking
        function_name: Name der Funktion für Logs
        
    Returns:
        list: Liste von Fragen-Objekten
    """
    try:
        # Verwende eine Liste für vorhandene Fragen, auch wenn None
        existing_q = existing_questions or []
        
        # Extrahiere Themen aus der Analyse
        main_topic = analysis.get('main_topic', 'Allgemeines Thema')
        subtopics = analysis.get('subtopics', [])
        
        # Erstelle eine Liste der bereits vorhandenen Fragen
        existing_questions_text = [q.get('question', '') for q in existing_q]
        
        # System-Prompt basierend auf der Sprache
        if language == 'de':
            system_content = """Du bist ein KI-Assistent, der beim Erstellen von Lernfragen hilft. 
            Deine Aufgabe ist es, anspruchsvolle und lehrreiche Fragen zu erstellen, die das Verständnis 
            des Themas fördern."""
            
            user_prompt = f"""Erstelle {num_to_generate} Lernfragen basierend auf dem folgenden Text. 
            Das Hauptthema ist "{main_topic}".
            
            Relevant sind folgende Themen:
            {', '.join(subtopics[:5]) if subtopics else main_topic}
            
            Folgende Fragen existieren bereits (erstelle keine Duplikate):
            {' | '.join(existing_questions_text[:10]) if existing_questions_text else "Keine"}
            
            Erstelle Fragen, die folgende Kriterien erfüllen:
            1. Eine Mischung aus verschiedenen Schwierigkeitsgraden
            2. Förderung von kritischem Denken und Verständnis
            3. Abdeckung verschiedener Aspekte des Themas
            4. Klarheit und Spezifität
            
            Gib deine Antwort als JSON-Array zurück. Jede Frage sollte diese Felder haben:
            - question: Die Frage
            - answer: Die ausführliche Antwort
            - difficulty: Die Schwierigkeit (easy, medium, hard)
            - topic: Das zugehörige Thema
            
            Hier ist der Text:
            {text[:5000]}"""
        else:
            system_content = """You are an AI assistant helping with creating study questions. 
            Your task is to create challenging and educational questions that promote understanding 
            of the topic."""
            
            user_prompt = f"""Create {num_to_generate} study questions based on the following text. 
            The main topic is "{main_topic}".
            
            Relevant topics include:
            {', '.join(subtopics[:5]) if subtopics else main_topic}
            
            The following questions already exist (don't create duplicates):
            {' | '.join(existing_questions_text[:10]) if existing_questions_text else "None"}
            
            Create questions that meet these criteria:
            1. A mix of different difficulty levels
            2. Promotion of critical thinking and understanding
            3. Coverage of different aspects of the topic
            4. Clarity and specificity
            
            Return your answer as a JSON array. Each question should have these fields:
            - question: The question
            - answer: The detailed answer
            - difficulty: The difficulty level (easy, medium, hard)
            - topic: The related topic
            
            Here's the text:
            {text[:5000]}"""
            
        # Sende die Anfrage an die KI
        response = query_chatgpt(
            prompt=user_prompt,
            client=client,
            system_content=system_content,
            temperature=0.7,
            use_cache=True,
            session_id=session_id,
            function_name=function_name
        )
        
        # Versuche, das JSON zu parsen
        try:
            # Entferne mögliche Markdown-Code-Blöcke
            json_text = re.sub(r'```json\s*|\s*```', '', response)
            questions = json.loads(json_text)
            
            # Stelle sicher, dass das Ergebnis eine Liste ist
            if isinstance(questions, dict) and 'questions' in questions:
                questions = questions['questions']
            elif not isinstance(questions, list):
                questions = [questions]
                
            # Validiere die Fragen
            valid_questions = []
            for q in questions:
                if isinstance(q, dict) and 'question' in q and 'answer' in q:
                    # Stelle sicher, dass alle erforderlichen Felder vorhanden sind
                    valid_q = {
                        'question': q.get('question', ''),
                        'answer': q.get('answer', ''),
                        'difficulty': q.get('difficulty', 'medium'),
                        'topic': q.get('topic', main_topic)
                    }
                    valid_questions.append(valid_q)
                    
            return valid_questions
        except Exception as e:
            logger.error(f"Fehler beim Parsen der Fragen: {str(e)}")
            logger.debug(f"AI-Antwort war: {response}")
            
            # Versuche, die Antwort manuell zu parsen
            try:
                # Suche nach Muster wie "1. Q: ..., A: ..." oder "Question: ...\nAnswer: ..."
                q_pattern = r'(?:Question:|Frage:|[QF]\d+:)\s*([^\n]+)(?:[\n,]\s*(?:Answer:|Antwort:|[AQ]\d+:)\s*([^\n]+))'
                matches = re.findall(q_pattern, response, re.IGNORECASE)
                
                if matches:
                    return [
                        {
                            'question': question.strip(),
                            'answer': answer.strip(),
                            'difficulty': 'medium',
                            'topic': main_topic
                        }
                        for question, answer in matches[:num_to_generate]
                    ]
            except Exception as e2:
                logger.error(f"Alternativer Parsing-Versuch fehlgeschlagen: {str(e2)}")
            
            # Fallback: Generiere einfache Standardfragen
            return [
                {
                    'question': f"Erkläre das Konzept von {main_topic}." if language == 'de' else f"Explain the concept of {main_topic}.",
                    'answer': "Konnte keine Antwort generieren" if language == 'de' else "Could not generate answer",
                    'difficulty': 'medium',
                    'topic': main_topic
                }
            ]
    except Exception as e:
        logger.error(f"Fehler bei der Generierung von Fragen: {str(e)}")
        
        # Generiere eine Standard-Frage
        default_question = f"Erkläre das Konzept von {main_topic}." if language == 'de' else f"Explain the concept of {main_topic}."
        default_answer = "Fehler bei der Generierung" if language == 'de' else "Error during generation"
        
        return [{
            'question': default_question,
            'answer': default_answer,
            'difficulty': 'medium',
            'topic': main_topic
        }]

def generate_quiz(text, client, topics=None, num_questions=5, language='en', session_id=None):
    """
    Generiert ein Quiz mit Multiple-Choice-Fragen basierend auf dem Text.
    
    Args:
        text: Der Quelltext
        client: Der OpenAI-Client
        topics: Optionale Themen, auf die sich das Quiz konzentrieren soll
        num_questions: Anzahl der zu generierenden Fragen
        language: Die Sprache des Textes ('en' oder 'de')
        session_id: Session-ID für Tracking
        
    Returns:
        list: Liste von Quiz-Fragen mit Antwortoptionen
    """
    try:
        # Erkenne die Sprache, falls nicht angegeben
        if not language:
            language = detect_language(text)
            
        # System-Prompt basierend auf der Sprache
        if language == 'de':
            system_content = """Du bist ein KI-Assistent, der beim Erstellen von Multiple-Choice-Quizfragen hilft. 
            Deine Aufgabe ist es, lehrreiche und klar formulierte Fragen mit plausiblen Antwortoptionen zu erstellen."""
            
            user_prompt = f"""Erstelle ein Quiz mit {num_questions} Multiple-Choice-Fragen basierend auf dem folgenden Text.
            
            {f'Fokussiere auf diese Themen: {", ".join(topics)}' if topics else ''}
            
            Jede Frage sollte haben:
            1. Eine klare, eindeutige Fragestellung
            2. Vier Antwortoptionen (A, B, C, D), von denen nur eine korrekt ist
            3. Die Kennzeichnung der korrekten Antwort
            4. Eine kurze Erklärung, warum die korrekte Antwort richtig ist
            
            Gib deine Antwort als JSON-Array zurück. Jede Quizfrage sollte diese Felder haben:
            - question: Die Frage
            - options: Ein Array mit den vier Antwortoptionen
            - correct_answer: Der Index der korrekten Antwort (0-3)
            - explanation: Die Erklärung für die korrekte Antwort
            
            Hier ist der Text:
            {text[:5000]}"""
        else:
            system_content = """You are an AI assistant helping with creating multiple-choice quiz questions. 
            Your task is to create educational and clearly formulated questions with plausible answer options."""
            
            user_prompt = f"""Create a quiz with {num_questions} multiple-choice questions based on the following text.
            
            {f'Focus on these topics: {", ".join(topics)}' if topics else ''}
            
            Each question should have:
            1. A clear, unambiguous question
            2. Four answer options (A, B, C, D), of which only one is correct
            3. Indication of the correct answer
            4. A brief explanation of why the correct answer is right
            
            Return your answer as a JSON array. Each quiz question should have these fields:
            - question: The question
            - options: An array with the four answer options
            - correct_answer: The index of the correct answer (0-3)
            - explanation: The explanation for the correct answer
            
            Here's the text:
            {text[:5000]}"""
            
        # Sende die Anfrage an die KI
        response = query_chatgpt(
            prompt=user_prompt,
            client=client,
            system_content=system_content,
            temperature=0.7,
            use_cache=True,
            session_id=session_id,
            function_name="generate_quiz"
        )
        
        # Versuche, das JSON zu parsen
        try:
            # Entferne mögliche Markdown-Code-Blöcke
            json_text = re.sub(r'```json\s*|\s*```', '', response)
            quiz_questions = json.loads(json_text)
            
            # Stelle sicher, dass das Ergebnis eine Liste ist
            if isinstance(quiz_questions, dict) and 'questions' in quiz_questions:
                quiz_questions = quiz_questions['questions']
            elif not isinstance(quiz_questions, list):
                quiz_questions = [quiz_questions]
                
            # Validiere die Quizfragen
            valid_questions = []
            for q in quiz_questions:
                if isinstance(q, dict) and 'question' in q and 'options' in q and 'correct_answer' in q:
                    # Stelle sicher, dass alle erforderlichen Felder vorhanden sind
                    valid_q = {
                        'question': q.get('question', ''),
                        'options': q.get('options', []),
                        'correct_answer': q.get('correct_answer', 0),
                        'explanation': q.get('explanation', '')
                    }
                    valid_questions.append(valid_q)
                    
            return valid_questions
        except Exception as e:
            logger.error(f"Fehler beim Parsen der Quizfragen: {str(e)}")
            
            # Fallback: Generiere eine einfache Quizfrage
            return [{
                'question': f"Was ist das Hauptthema des Textes?" if language == 'de' else f"What is the main topic of the text?",
                'options': [
                    "Option A",
                    "Option B",
                    "Option C",
                    "Option D"
                ],
                'correct_answer': 0,
                'explanation': "Fehler bei der Generierung" if language == 'de' else "Error during generation"
            }]
    except Exception as e:
        logger.error(f"Fehler bei der Generierung des Quizzes: {str(e)}")
        
        # Generiere eine Standard-Quizfrage
        return [{
            'question': f"Was ist das Hauptthema des Textes?" if language == 'de' else f"What is the main topic of the text?",
            'options': [
                "Option A",
                "Option B",
                "Option C",
                "Option D"
            ],
            'correct_answer': 0,
            'explanation': "Fehler bei der Generierung" if language == 'de' else "Error during generation"
        }] 