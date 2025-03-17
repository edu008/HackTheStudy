import json
import re
import PyPDF2
import docx
from langdetect import detect
import io  # Hinzugefügt für BytesIO

def allowed_file(filename):
    allowed_extensions = {'pdf', 'txt', 'docx', 'doc'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def extract_text_from_file(file, filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext == 'pdf':
        try:
            # Konvertiere bytes in ein file-like Objekt
            file_like = io.BytesIO(file)
            pdf_reader = PyPDF2.PdfReader(file_like)
            text = "".join(page.extract_text() + "\n" for page in pdf_reader.pages if page.extract_text())
            return text
        except Exception as e:
            return f"Error extracting text from PDF: {str(e)}"
    elif ext == 'docx':
        try:
            doc = docx.Document(file)
            text = "".join(para.text + "\n" for para in doc.paragraphs)
            return text
        except Exception as e:
            return f"Error extracting text from DOCX: {str(e)}"
    elif ext == 'txt':
        try:
            return file.read().decode('utf-8', errors='ignore')
        except Exception as e:
            return f"Error decoding text file: {str(e)}"
    return f"Unsupported file format: {ext}"

def detect_language(text):
    try:
        lang = detect(text[:500])  # Begrenze auf 500 Zeichen für Effizienz
        return 'de' if lang == 'de' else 'en'
    except Exception:
        return 'en'

def query_chatgpt(prompt, client, system_content=None):
    try:
        messages = []
        if system_content:
            messages.append({"role": "system", "content": system_content})
        else:
            messages.append({"role": "system", "content": "You are a helpful assistant that provides concise, accurate information."})
        messages.append({"role": "user", "content": prompt})
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-16k",
            messages=messages,
            temperature=0.9,
            max_tokens=4000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error querying OpenAI API: {str(e)}"

def analyze_content(text, client, language='en'):
    system_content = (
        "You are an expert in educational content analysis. Your task is to analyze the provided text and extract key information for generating study materials."
        if language != 'de' else
        "Sie sind ein Experte für die Analyse von Bildungsinhalten. Ihre Aufgabe ist es, den bereitgestellten Text zu analysieren und wichtige Informationen für die Erstellung von Lernmaterialien zu extrahieren."
    )
    
    prompt = (
        """
        Analyze the following text and extract the following information:
        1. The main topic of the text (a concise phrase)
        2. 3-7 important subtopics or concepts (as an array)
        3. An estimate of how many flashcards would be useful (between 5-20, as a number)
        4. An estimate of how many test questions would be useful (between 3-10, as a number)
        5. A list of existing questions in the text (if any, otherwise empty array)
        6. The content type (e.g., 'lecture', 'textbook', 'notes', 'scientific article')

        Format your response as JSON with the keys: main_topic, subtopics, estimated_flashcards, estimated_questions, existing_questions, content_type.

        Text:
        """
        if language != 'de' else
        """
        Analysieren Sie den folgenden Text und extrahieren Sie die folgenden Informationen:
        1. Das Hauptthema des Textes (eine prägnante Phrase)
        2. 3-7 wichtige Unterthemen oder Konzepte (als Array)
        3. Eine Schätzung, wie viele Karteikarten sinnvoll wären (zwischen 5-20, als Zahl)
        4. Eine Schätzung, wie viele Testfragen sinnvoll wären (zwischen 3-10, als Zahl)
        5. Eine Liste von existierenden Fragen im Text (falls vorhanden, sonst leeres Array)
        6. Den Inhaltstyp (z.B. 'Vorlesung', 'Lehrbuch', 'Notizen', 'Wissenschaftlicher Artikel')

        Formatieren Sie Ihre Antwort als JSON mit den Schlüsseln: main_topic, subtopics, estimated_flashcards, estimated_questions, existing_questions, content_type.

        Text:
        """
    )
    
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"
    
    response = query_chatgpt(prompt + text, client, system_content)
    
    try:
        result = json.loads(response)
        expected_keys = ['main_topic', 'subtopics', 'estimated_flashcards', 'estimated_questions', 'existing_questions', 'content_type']
        for key in expected_keys:
            if key not in result:
                result[key] = [] if key in ['subtopics', 'existing_questions'] else "" if key == 'main_topic' else "unknown" if key == 'content_type' else 0
        return result
    except json.JSONDecodeError:
        main_topic_match = re.search(r'"main_topic"\s*:\s*"([^"]+)"', response)
        subtopics_match = re.search(r'"subtopics"\s*:\s*\[(.*?)\]', response, re.DOTALL)
        flashcards_match = re.search(r'"estimated_flashcards"\s*:\s*(\d+)', response)
        questions_match = re.search(r'"estimated_questions"\s*:\s*(\d+)', response)
        
        main_topic = main_topic_match.group(1) if main_topic_match else "Unknown Topic"
        subtopics_str = subtopics_match.group(1) if subtopics_match else ""
        subtopics = [s.strip(' "\'') for s in subtopics_str.split(',') if s.strip(' "\'')]
        estimated_flashcards = int(flashcards_match.group(1)) if flashcards_match else 10
        estimated_questions = int(questions_match.group(1)) if questions_match else 5
        
        return {
            'main_topic': main_topic,
            'subtopics': subtopics,
            'estimated_flashcards': estimated_flashcards,
            'estimated_questions': estimated_questions,
            'existing_questions': [],
            'content_type': "unknown"
        }

def generate_flashcards(text, client, analysis=None, existing_flashcards=None, language='en'):
    system_content = (
        "You are an expert in creating educational flashcards. Generate concise, clear, and unique question-answer pairs based on the provided text."
        if language != 'de' else
        "Sie sind ein Experte für die Erstellung von Lernkarteikarten. Erstellen Sie prägnante, klare und einzigartige Frage-Antwort-Paare basierend auf dem bereitgestellten Text."
    )
    
    prompt = (
        """
        Create flashcards for the following material. Each flashcard should have a question and an answer.
        The questions should cover important concepts and the answers should be precise and informative.
        Format your response as a JSON array of objects with the keys "question" and "answer".
        """
        if language != 'de' else
        """
        Erstelle Karteikarten für das folgende Material. Jede Karteikarte sollte eine Frage und eine Antwort enthalten.
        Die Fragen sollten wichtige Konzepte abdecken und die Antworten sollten präzise und informativ sein.
        Formatiere deine Antwort als JSON-Array mit Objekten, die die Schlüssel "question" und "answer" enthalten.
        """
    )
    
    if analysis:
        prompt += (
            f"\n\nMain topic: {analysis.get('main_topic', '')}\nSubtopics: {', '.join(analysis.get('subtopics', []))}\n"
            if language != 'de' else
            f"\n\nHauptthema: {analysis.get('main_topic', '')}\nUnterthemen: {', '.join(analysis.get('subtopics', []))}\n"
        )
    
    if existing_flashcards:
        prompt += (
            f"\n\nExisting flashcards (do not create duplicates):\n{json.dumps(existing_flashcards[:10])}\n"
            if language != 'de' else
            f"\n\nBereits vorhandene Karteikarten (erstelle keine Duplikate):\n{json.dumps(existing_flashcards[:10])}\n"
        )
    
    num_flashcards = min(analysis.get('estimated_flashcards', 10), 15) if analysis else 10
    prompt += (
        f"\nCreate {num_flashcards} flashcards for the following text:\n\n"
        if language != 'de' else
        f"\nErstelle {num_flashcards} Karteikarten für den folgenden Text:\n\n"
    )
    
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"
    
    response = query_chatgpt(prompt + text, client, system_content)
    
    try:
        flashcards = json.loads(response)
        if not isinstance(flashcards, list):
            raise ValueError("Response is not a list")
        return [fc for fc in flashcards if isinstance(fc, dict) and 'question' in fc and 'answer' in fc]
    except (json.JSONDecodeError, ValueError):
        pattern = r'(?:Q:|"question":\s*")(.*?)(?:"\s*,|\n\s*A:)(?:\s*"answer":\s*"|\s*)(.*?)(?:"\s*}|(?=\n\s*Q:|$))'
        matches = re.findall(pattern, response, re.DOTALL)
        flashcards = [{"question": q.strip().strip('"'), "answer": a.strip().strip('"')} for q, a in matches if q and a]
        return flashcards if flashcards else [{"question": "Could not generate flashcards", "answer": "Please try again"}]

def generate_test_questions(text, client, analysis=None, existing_questions_list=None, language='en'):
    system_content = (
        """
        You are an expert in creating exam questions. Your task is to create COMPLETELY NEW multiple-choice test questions that are FUNDAMENTALLY different from the existing questions.
        - Each new question MUST cover a different concept or topic than the existing questions.
        - NEVER use similar phrasings or structures as the existing questions.
        - Focus on untouched aspects of the text.
        - Return fewer questions if completely new ones cannot be created.
        """
        if language != 'de' else
        """
        Sie sind ein Experte für die Erstellung von Testfragen. Ihre Aufgabe ist es, KOMPLETT NEUE Multiple-Choice-Fragen zu erstellen, die sich GRUNDLEGEND von den vorhandenen Fragen unterscheiden.
        - Jede neue Frage MUSS ein anderes Konzept oder Thema behandeln als die vorhandenen Fragen.
        - Verwenden Sie NIEMALS ähnliche Formulierungen oder Strukturen wie bei den vorhandenen Fragen.
        - Konzentrieren Sie sich auf unberührte Aspekte des Textes.
        - Geben Sie weniger Fragen zurück, wenn keine völlig neuen erstellt werden können.
        """
    )
    
    prompt = (
        """
        Create multiple-choice test questions for the following material. Each question should have 4 options with only one correct answer.
        Format your response as a JSON array of objects with the keys "text", "options", "correct", and "explanation".
        """
        if language != 'de' else
        """
        Erstelle Multiple-Choice-Testfragen für das folgende Material. Jede Frage sollte 4 Antwortmöglichkeiten haben, wobei nur eine korrekt ist.
        Formatiere deine Antwort als JSON-Array mit Objekten, die die Schlüssel "text", "options", "correct" und "explanation" enthalten.
        """
    )
    
    if analysis:
        prompt += (
            f"\n\nMain topic: {analysis.get('main_topic', '')}\nSubtopics: {', '.join(analysis.get('subtopics', []))}\n"
            if language != 'de' else
            f"\n\nHauptthema: {analysis.get('main_topic', '')}\nUnterthemen: {', '.join(analysis.get('subtopics', []))}\n"
        )
    
    if existing_questions_list:
        prompt += (
            "\n\n### EXISTING QUESTIONS (DO NOT CREATE SIMILAR QUESTIONS) ###\n"
            if language != 'de' else
            "\n\n### BEREITS VORHANDENE FRAGEN (ERSTELLE KEINE ÄHNLICHEN FRAGEN) ###\n"
        )
        for i, q in enumerate(existing_questions_list):
            prompt += f"{i+1}. {q.get('text', '')}\n"
        prompt += (
            "\nCreate COMPLETELY NEW questions covering different aspects of the text.\n"
            if language != 'de' else
            "\nErstelle KOMPLETT NEUE Fragen, die andere Aspekte des Textes abdecken.\n"
        )
    
    num_questions = min(analysis.get('estimated_questions', 5), 8) if analysis else 5
    prompt += (
        f"\nCreate {num_questions} test questions for the following text:\n\n"
        if language != 'de' else
        f"\nErstelle {num_questions} Testfragen für den folgenden Text:\n\n"
    )
    
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"
    
    response = query_chatgpt(prompt + text, client, system_content)
    
    try:
        questions = json.loads(response)
        if not isinstance(questions, list):
            raise ValueError("Response is not a list")
        return [q for q in questions if isinstance(q, dict) and 'text' in q and 'options' in q and 'correct' in q]
    except (json.JSONDecodeError, ValueError):
        pattern = r'(?:"text":\s*")(.*?)(?:")\s*,\s*"options":\s*\[(.*?)\]\s*,\s*"correct"\s*:\s*(\d+)'
        matches = re.findall(pattern, response, re.DOTALL)
        questions = []
        for text, options_str, correct in matches:
            options = re.findall(r'"([^"]*)"', options_str)
            if len(options) >= 2:
                questions.append({
                    "text": text,
                    "options": options,
                    "correct": int(correct),
                    "explanation": ""
                })
        return questions if questions else [{"text": "Could not generate test questions", "options": ["Try again"], "correct": 0, "explanation": ""}]