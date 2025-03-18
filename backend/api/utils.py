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

def query_chatgpt(prompt, client, system_content=None, temperature=0.7):
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
            temperature=temperature,  # Standard-Temperatur von 0.7, kann überschrieben werden
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

def filter_visual_references(items, is_flashcard=True):
    """Filtert Fragen oder Antworten mit Bezug zu visuellen Hilfsmitteln."""
    visual_keywords = ['diagram', 'figure', 'table', 'graph', 'chart', 'image', 'illustration', 'visual']
    if is_flashcard:
        return [
            item for item in items
            if all(keyword not in item.get('question', '').lower() and keyword not in item.get('answer', '').lower()
                   for keyword in visual_keywords)
        ]
    else:
        return [
            item for item in items
            if all(keyword not in item.get('text', '').lower() and keyword not in ' '.join(item.get('options', [])).lower()
                   and keyword not in item.get('explanation', '').lower() for keyword in visual_keywords)
        ]


def generate_flashcards(text, client, analysis=None, existing_flashcards=None, language='en'):
    system_content = (
        """
        You are an expert in creating educational flashcards. Your task is to generate COMPLETELY NEW, ORIGINAL flashcards that are FUNDAMENTALLY DIFFERENT from any existing ones.
        
        CRITICAL INSTRUCTIONS:
        - IGNORE the existing flashcards completely except to ensure you don't create anything similar.
        - DO NOT use the existing flashcards as templates or inspiration.
        - CREATE ENTIRELY NEW content based on the subtopics provided.
        - INVENT new scenarios, examples, and applications related to the subtopics.
        - Each flashcard must cover a DIFFERENT ASPECT of the subject matter than both existing flashcards AND other new flashcards you create.
        - Use DIFFERENT question formats, structures, and approaches for each flashcard.
        - If you've created a definition-style question, don't create another one. If you've created a comparison question, don't create another one.
        - VARY your language patterns, sentence structures, and terminology significantly.
        - FOCUS on creating flashcards that explore the subtopics from completely different angles and perspectives.
        - Base your questions and answers on the text provided, but if the text lacks specific information, invent plausible, hypothetical scenarios that are thematically consistent with the main topic and subtopics.
        - Ensure that every question has a clear, informative answer. Do NOT return answers like "Unknown" or "Not provided in the text."
        - Do NOT generate any questions or answers that mention, imply, refer to, or depend on diagrams, figures, tables, graphs, charts, images, illustrations, or any other visual aids.
        - Every question and answer MUST be fully standalone, self-contained, and understandable without any visual context or additional resources beyond the provided text.
        """
        if language != 'de' else
        """
        Sie sind ein Experte für die Erstellung von Lernkarteikarten. Ihre Aufgabe ist es, KOMPLETT NEUE, ORIGINALE Karteikarten zu erstellen, die sich GRUNDLEGEND von allen vorhandenen unterscheiden.
        
        KRITISCHE ANWEISUNGEN:
        - IGNORIEREN Sie die vorhandenen Karteikarten vollständig, außer um sicherzustellen, dass Sie nichts Ähnliches erstellen.
        - Verwenden Sie die vorhandenen Karteikarten NICHT als Vorlagen oder Inspiration.
        - ERSTELLEN Sie VÖLLIG NEUE Inhalte basierend auf den bereitgestellten Unterthemen.
        - ERFINDEN Sie neue Szenarien, Beispiele und Anwendungen im Zusammenhang mit den Unterthemen.
        - Jede Karteikarte muss einen ANDEREN ASPEKT des Themas abdecken als sowohl die vorhandenen Karteikarten ALS AUCH andere neue Karteikarten, die Sie erstellen.
        - Verwenden Sie für jede Karteikarte UNTERSCHIEDLICHE Frageformate, Strukturen und Ansätze.
        - Wenn Sie eine Definitionsfrage erstellt haben, erstellen Sie keine weitere. Wenn Sie eine Vergleichsfrage erstellt haben, erstellen Sie keine weitere.
        - VARIIEREN Sie Ihre Sprachmuster, Satzstrukturen und Terminologie erheblich.
        - KONZENTRIEREN Sie sich darauf, Karteikarten zu erstellen, die die Unterthemen aus völlig verschiedenen Blickwinkeln und Perspektiven untersuchen.
        - Stützen Sie Ihre Fragen und Antworten auf den bereitgestellten Text, aber wenn der Text keine spezifischen Informationen enthält, erfinden Sie plausible, hypothetische Szenarien, die thematisch mit dem Hauptthema und den Unterthemen übereinstimmen.
        - Stellen Sie sicher, dass jede Frage eine klare, informative Antwort hat. Geben Sie KEINE Antworten wie "Unbekannt" oder "Nicht im Text angegeben" zurück.
        - Erstellen Sie KEINE Fragen oder Antworten, die Diagramme, Abbildungen, Tabellen, Grafiken, Diagramme, Bilder, Illustrationen oder andere visuelle Hilfsmittel erwähnen, andeuten, darauf verweisen oder davon abhängen.
        - Jede Frage und Antwort MUSS vollständig eigenständig, in sich geschlossen und verständlich sein, ohne jeglichen visuellen Kontext oder zusätzliche Ressourcen außer dem bereitgestellten Text.
        """
    )

    prompt = (
        """
        Create COMPLETELY NEW and ORIGINAL flashcards for the following material. Each flashcard should have a question and an answer.
        
        IMPORTANT INSTRUCTIONS:
        - FOCUS on the subtopics provided and create flashcards that explore different aspects of these subtopics.
        - CREATE flashcards that are COMPLETELY DIFFERENT from any existing ones in content, structure, and approach.
        - INVENT new scenarios, examples, and applications related to the subtopics.
        - USE a wide variety of question types: definitions, comparisons, applications, analyses, evaluations, etc.
        - VARY your language patterns, sentence structures, and terminology significantly between flashcards.
        - DO NOT follow patterns from existing flashcards - create entirely new patterns.
        - Base questions and answers on key concepts in the text. If the text does not provide enough information to answer a question, invent a plausible, hypothetical scenario that aligns with the main topic and subtopics to provide a clear, informative answer.
        - Do NOT return answers like "Unknown" or "Not provided in the text." Instead, create a reasonable scenario based on the themes of the text.
        - Do NOT include any questions or answers that mention, imply, or rely on diagrams, figures, tables, graphs, charts, images, illustrations, or any other visual aids.
        - Answers must be precise, informative, and fully self-contained, with NO references to visual elements or external context.
        - Format your response as a JSON array of objects with the keys "question" and "answer".
        
        EXAMPLES OF DIFFERENT QUESTION TYPES TO USE (create your own, don't copy these):
        - "How would [concept] be applied in [novel scenario]?"
        - "Compare and contrast [concept A] with [concept B] in terms of [aspect]."
        - "What would be the implications of [hypothetical scenario related to subtopic]?"
        - "Explain the relationship between [concept A] and [concept B] in the context of [subtopic]."
        - "What are three key factors that influence [process related to subtopic]?"
        """
        if language != 'de' else
        """
        Erstellen Sie KOMPLETT NEUE und ORIGINALE Karteikarten für das folgende Material. Jede Karteikarte sollte eine Frage und eine Antwort enthalten.
        
        WICHTIGE ANWEISUNGEN:
        - KONZENTRIEREN Sie sich auf die bereitgestellten Unterthemen und erstellen Sie Karteikarten, die verschiedene Aspekte dieser Unterthemen untersuchen.
        - ERSTELLEN Sie Karteikarten, die sich in Inhalt, Struktur und Ansatz VOLLSTÄNDIG von allen vorhandenen unterscheiden.
        - ERFINDEN Sie neue Szenarien, Beispiele und Anwendungen im Zusammenhang mit den Unterthemen.
        - VERWENDEN Sie eine große Vielfalt an Fragetypen: Definitionen, Vergleiche, Anwendungen, Analysen, Bewertungen usw.
        - VARIIEREN Sie Ihre Sprachmuster, Satzstrukturen und Terminologie erheblich zwischen den Karteikarten.
        - Folgen Sie NICHT den Mustern vorhandener Karteikarten - erstellen Sie völlig neue Muster.
        - Stützen Sie Fragen und Antworten auf Schlüsselkonzepte im Text. Wenn der Text nicht genügend Informationen zur Beantwortung einer Frage bietet, erfinden Sie ein plausibles, hypothetisches Szenario, das mit dem Hauptthema und den Unterthemen übereinstimmt, um eine klare, informative Antwort zu geben.
        - Geben Sie KEINE Antworten wie "Unbekannt" oder "Nicht im Text angegeben" zurück. Erfinden Sie stattdessen ein vernünftiges Szenario basierend auf den Themen des Textes.
        - Fügen Sie KEINE Fragen oder Antworten hinzu, die Diagramme, Abbildungen, Tabellen, Grafiken, Diagramme, Bilder, Illustrationen oder andere visuelle Hilfsmittel erwähnen, andeuten oder darauf angewiesen sind.
        - Die Antworten müssen präzise, informativ und vollständig eigenständig sein, OHNE Verweise auf visuelle Elemente oder externen Kontext.
        - Formatieren Sie Ihre Antwort als JSON-Array mit Objekten, die die Schlüssel "question" und "answer" enthalten.
        
        BEISPIELE FÜR VERSCHIEDENE FRAGETYPEN (erstellen Sie Ihre eigenen, kopieren Sie diese nicht):
        - "Wie würde [Konzept] in [neuartiges Szenario] angewendet werden?"
        - "Vergleichen und kontrastieren Sie [Konzept A] mit [Konzept B] in Bezug auf [Aspekt]."
        - "Was wären die Auswirkungen von [hypothetisches Szenario im Zusammenhang mit Unterthema]?"
        - "Erklären Sie die Beziehung zwischen [Konzept A] und [Konzept B] im Kontext von [Unterthema]."
        - "Was sind drei Schlüsselfaktoren, die [Prozess im Zusammenhang mit Unterthema] beeinflussen?"
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
            "\n\n### EXISTING FLASHCARDS (DO NOT REUSE THESE EXACT QUESTIONS OR CREATE SIMILAR ONES) ###\n"
            if language != 'de' else
            "\n\n### BEREITS VORHANDENE KARTEIKARTEN (VERWENDEN SIE DIESE GENAUEN FRAGEN NICHT ODER ERSTELLEN SIE ÄHNLICHE) ###\n"
        )
        for i, f in enumerate(existing_flashcards):
            prompt += f"{i+1}. Question: {f.get('question', '')}\n   Answer: {f.get('answer', '')}\n"
        prompt += (
            "\nCreate COMPLETELY NEW flashcards with entirely different structures, numbers, contexts, and topics, avoiding any similarity to the above existing flashcards.\n"
            if language != 'de' else
            "\nErstellen Sie KOMPLETT NEUE Karteikarten mit völlig anderen Strukturen, Zahlen, Kontexten und Themen, und vermeiden Sie jede Ähnlichkeit mit den oben genannten vorhandenen Karteikarten.\n"
        )

    num_flashcards = min(analysis.get('estimated_flashcards', 10), 15) if analysis else 10
    prompt += (
        f"\nCreate {num_flashcards} flashcards for the following text:\n\n"
        if language != 'de' else
        f"\nErstellen Sie {num_flashcards} Karteikarten für den folgenden Text:\n\n"
    )

    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"

    # Erhöhe die Temperatur für mehr Kreativität
    response = query_chatgpt(prompt + text, client, system_content, temperature=0.9)

    try:
        flashcards = json.loads(response)
        if not isinstance(flashcards, list):
            raise ValueError("Response is not a list")
        valid_flashcards = [fc for fc in flashcards if isinstance(fc, dict) and 'question' in fc and 'answer' in fc]
        return filter_visual_references(valid_flashcards, is_flashcard=True)
    except (json.JSONDecodeError, ValueError):
        pattern = r'(?:Q:|"question":\s*")(.*?)(?:"\s*,|\n\s*A:)(?:\s*"answer":\s*"|\s*)(.*?)(?:"\s*}|(?=\n\s*Q:|$))'
        matches = re.findall(pattern, response, re.DOTALL)
        flashcards = [{"question": q.strip().strip('"'), "answer": a.strip().strip('"')} for q, a in matches if q and a]
        return filter_visual_references(flashcards, is_flashcard=True) if flashcards else [{"question": "Could not generate flashcards", "answer": "Please try again"}]


# ... (andere Funktionen wie allowed_file, extract_text_from_file, etc. bleiben gleich)

def generate_test_questions(text, client, analysis=None, existing_questions_list=None, language='en'):
    system_content = (
        """
        You are an expert in creating exam questions. Your task is to create COMPLETELY NEW and ORIGINAL multiple-choice test questions that are FUNDAMENTALLY DIFFERENT from any existing questions.
        
        CRITICAL INSTRUCTIONS:
        - IGNORE the existing questions completely except to ensure you don't create anything similar.
        - DO NOT use the existing questions as templates or inspiration.
        - CREATE ENTIRELY NEW content based on the subtopics provided.
        - INVENT new scenarios, examples, and applications related to the subtopics.
        - Each question must cover a DIFFERENT ASPECT of the subject matter than both existing questions AND other new questions you create.
        - Use DIFFERENT question formats, structures, and approaches for each question.
        - If you've created a factual recall question, don't create another one. If you've created an application question, don't create another one.
        - VARY your language patterns, sentence structures, and terminology significantly.
        - FOCUS on creating questions that explore the subtopics from completely different angles and perspectives.
        - Base your questions and answers on the text provided, but if the text lacks specific information, invent plausible, hypothetical scenarios that are thematically consistent with the main topic and subtopics.
        - Ensure that every question has a clear, informative answer with a correct option. Do NOT return answers or explanations like "Unknown" or "Not provided in the text."
        - Do NOT generate any questions, options, or explanations that mention, imply, refer to, or depend on diagrams, figures, tables, graphs, charts, images, illustrations, or any other visual aids.
        - Every question, its options, and explanation MUST be fully standalone, self-contained, and understandable without any visual context or additional resources beyond the provided text.
        - The "correct" value MUST be an integer (0-3) representing the index of the correct option in the "options" array, NOT the text of the answer.
        """
        if language != 'de' else
        """
        Sie sind ein Experte für die Erstellung von Testfragen. Ihre Aufgabe ist es, KOMPLETT NEUE und ORIGINALE Multiple-Choice-Fragen zu erstellen, die sich GRUNDLEGEND von allen vorhandenen Fragen unterscheiden.
        
        KRITISCHE ANWEISUNGEN:
        - IGNORIEREN Sie die vorhandenen Fragen vollständig, außer um sicherzustellen, dass Sie nichts Ähnliches erstellen.
        - Verwenden Sie die vorhandenen Fragen NICHT als Vorlagen oder Inspiration.
        - ERSTELLEN Sie VÖLLIG NEUE Inhalte basierend auf den bereitgestellten Unterthemen.
        - ERFINDEN Sie neue Szenarien, Beispiele und Anwendungen im Zusammenhang mit den Unterthemen.
        - Jede Frage muss einen ANDEREN ASPEKT des Themas abdecken als sowohl die vorhandenen Fragen ALS AUCH andere neue Fragen, die Sie erstellen.
        - Verwenden Sie für jede Frage UNTERSCHIEDLICHE Frageformate, Strukturen und Ansätze.
        - Wenn Sie eine Faktenwissensfrage erstellt haben, erstellen Sie keine weitere. Wenn Sie eine Anwendungsfrage erstellt haben, erstellen Sie keine weitere.
        - VARIIEREN Sie Ihre Sprachmuster, Satzstrukturen und Terminologie erheblich.
        - KONZENTRIEREN Sie sich darauf, Fragen zu erstellen, die die Unterthemen aus völlig verschiedenen Blickwinkeln und Perspektiven untersuchen.
        - Stützen Sie Ihre Fragen und Antworten auf den bereitgestellten Text, aber wenn der Text keine spezifischen Informationen enthält, erfinden Sie plausible, hypothetische Szenarien, die thematisch mit dem Hauptthema und den Unterthemen übereinstimmen.
        - Stellen Sie sicher, dass jede Frage eine klare, informative Antwort mit einer korrekten Option hat. Geben Sie KEINE Antworten oder Erklärungen wie "Unbekannt" oder "Nicht im Text angegeben" zurück.
        - Erstellen Sie KEINE Fragen, Optionen oder Erklärungen, die Diagramme, Abbildungen, Tabellen, Grafiken, Diagramme, Bilder, Illustrationen oder andere visuelle Hilfsmittel erwähnen, andeuten, darauf verweisen oder davon abhängen.
        - Jede Frage, ihre Optionen und Erklärung MUSS vollständig eigenständig, in sich geschlossen und verständlich sein, ohne jeglichen visuellen Kontext oder zusätzliche Ressourcen außer dem bereitgestellten Text.
        - Der "correct"-Wert MUSS eine Ganzzahl (0-3) sein, die den Index der richtigen Option im "options"-Array angibt, NICHT der Text der Antwort.
        """
    )

    prompt = (
        """
        Create multiple-choice test questions for the following material. Each question should have 4 options with only one correct answer.
        - Base questions and answers on key concepts in the text. If the text does not provide enough information to answer a question, invent a plausible, hypothetical scenario that aligns with the main topic and subtopics to provide a clear, informative answer.
        - Do NOT return answers or explanations like "Unknown" or "Not provided in the text." Instead, create a reasonable scenario based on the themes of the text.
        - Do NOT include any questions, options, or explanations that mention, imply, or rely on diagrams, figures, tables, graphs, charts, images, illustrations, or any other visual aids.
        - Options and explanations must be precise, informative, and fully self-contained, with NO references to visual elements or external context.
        - To ensure MAXIMUM VARIETY, invent entirely new, hypothetical scenarios or examples related to the main topic and subtopics, even if they are not explicitly mentioned in the text. These scenarios MUST be highly creative, with significantly different contexts, numbers, and phrasings compared to existing questions.
        - Analyze the existing questions (if provided) and ensure that no new questions repeat the exact wording, structure, numbers, or context of the existing questions. The new questions MUST be distinctly different in every aspect. For example:
          - If an existing question is "What is the effect of an increase in demand for mandatory health insurance in Switzerland?", do NOT create questions about Switzerland, health insurance demand increases, or similar structures. Instead, use a different country (e.g., Germany) and a different context (e.g., tax policy effects on healthcare).
          - If an existing question uses numbers like "4.5 million" or "30 EURO", avoid these numbers and use entirely different values (e.g., "200,000 units" or "15% tax").
          - If an existing question uses a phrase like "What is the effect of...", use a different structure (e.g., "How would a policy impact..." or "What are the consequences of...").
        - Format your response as a JSON array of objects with the keys "text", "options", "correct" (an integer 0-3), and "explanation".
        """
        if language != 'de' else
        """
        Erstellen Sie Multiple-Choice-Testfragen für das folgende Material. Jede Frage sollte 4 Antwortmöglichkeiten haben, wobei nur eine korrekt ist.
        - Stützen Sie Fragen und Antworten auf Schlüsselkonzepte im Text. Wenn der Text nicht genügend Informationen zur Beantwortung einer Frage bietet, erfinden Sie ein plausibles, hypothetisches Szenario, das mit dem Hauptthema und den Unterthemen übereinstimmt, um eine klare, informative Antwort zu geben.
        - Geben Sie KEINE Antworten oder Erklärungen wie "Unbekannt" oder "Nicht im Text angegeben" zurück. Erfinden Sie stattdessen ein vernünftiges Szenario basierend auf den Themen des Textes.
        - Fügen Sie KEINE Fragen, Optionen oder Erklärungen hinzu, die Diagramme, Abbildungen, Tabellen, Grafiken, Diagramme, Bilder, Illustrationen oder andere visuelle Hilfsmittel erwähnen, andeuten oder darauf angewiesen sind.
        - Die Optionen und Erklärungen müssen präzise, informativ und vollständig eigenständig sein, OHNE Verweise auf visuelle Elemente oder externen Kontext.
        - Um SICHERE Abwechslung zu gewährleisten, erfinden Sie völlig neue, hypothetische Szenarien oder Beispiele, die sich auf das Hauptthema und die Unterthemen beziehen, auch wenn sie nicht explizit im Text erwähnt sind. Diese Szenarien MÜSSEN hoch kreativ sein und sich deutlich in Kontext, Zahlen und Formulierungen von bestehenden Fragen unterscheiden.
        - Analysieren Sie die bestehenden Fragen (falls vorhanden) und stellen Sie sicher, dass keine neuen Fragen die genaue Wortwahl, Struktur, Zahlen oder Kontexte der vorhandenen Fragen wiederholen. Die neuen Fragen MÜSSEN in jedem Aspekt eindeutig unterschiedlich sein. Zum Beispiel:
          - Wenn eine vorhandene Frage lautet "What is the effect of an increase in demand for mandatory health insurance in Switzerland?", erstellen Sie KEINE Fragen über die Schweiz, Nachfrageerhöhungen bei Krankenversicherungen oder ähnliche Strukturen. Nutzen Sie stattdessen ein anderes Land (z. B. Deutschland) und einen anderen Kontext (z. B. Steuerpolitik-Effekte auf Gesundheitswesen).
          - Wenn eine vorhandene Frage Zahlen wie "4,5 Millionen" oder "30 EURO" verwendet, vermeiden Sie diese Zahlen und nutzen Sie völlig andere Werte (z. B. "200.000 Einheiten" oder "15% Steuer").
          - Wenn eine vorhandene Frage eine Formulierung wie "What is the effect of..." verwendet, nutzen Sie eine andere Struktur (z. B. "Wie würde eine Politik beeinflussen..." oder "Welche Folgen hat...").
        - Formatieren Sie Ihre Antwort als JSON-Array mit Objekten, die die Schlüssel "text", "options", "correct" (eine Ganzzahl 0-3) und "explanation" enthalten.
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
            "\n\n### EXISTING QUESTIONS (DO NOT REUSE THESE EXACT QUESTIONS OR CREATE SIMILAR ONES) ###\n"
            if language != 'de' else
            "\n\n### BEREITS VORHANDENE FRAGEN (VERWENDEN SIE DIESE GENAUEN FRAGEN NICHT ODER ERSTELLEN SIE ÄHNLICHE) ###\n"
        )
        for i, q in enumerate(existing_questions_list):
            prompt += f"{i+1}. {q.get('text', '')}\n"
        prompt += (
            "\nCreate COMPLETELY NEW questions with entirely different structures, numbers, contexts, and topics, avoiding any similarity to the above existing questions.\n"
            if language != 'de' else
            "\nErstellen Sie KOMPLETT NEUE Fragen mit völlig anderen Strukturen, Zahlen, Kontexten und Themen, und vermeiden Sie jede Ähnlichkeit mit den oben genannten vorhandenen Fragen.\n"
        )

    num_questions = min(analysis.get('estimated_questions', 5), 8) if analysis else 5
    prompt += (
        f"\nCreate {num_questions} test questions for the following text:\n\n"
        if language != 'de' else
        f"\nErstellen Sie {num_questions} Testfragen für den folgenden Text:\n\n"
    )

    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"

    # Erhöhe die Temperatur für mehr Kreativität
    response = query_chatgpt(prompt + text, client, system_content, temperature=0.9)

    try:
        questions = json.loads(response)
        if not isinstance(questions, list):
            raise ValueError("Response is not a list")
        valid_questions = [q for q in questions if isinstance(q, dict) and 'text' in q and 'options' in q and 'correct' in q]
        return filter_visual_references(valid_questions, is_flashcard=False)
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
        return filter_visual_references(questions, is_flashcard=False) if questions else [{"text": "Could not generate test questions", "options": ["Try again"], "correct": 0, "explanation": ""}]
