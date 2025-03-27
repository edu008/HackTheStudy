"""
Generierung von Fragen
-------------------

Dieses Modul enthält Funktionen für die Generierung von Fragen
auf Basis von Uploads und Analysen.
"""

import logging
import random
import json
from flask import current_app
from openai import OpenAI
from api.token_tracking import check_credits_available, calculate_token_cost, deduct_credits
from ..utils import query_chatgpt
from .utils import count_tokens, detect_language_wrapper, calculate_generation_cost

logger = logging.getLogger(__name__)

def generate_questions(content, count=10, analysis=None, language='en'):
    """
    Generiert Fragen auf Basis eines Inhalts und einer optionalen Analyse.
    
    Args:
        content: Der Inhalt, auf dessen Basis Fragen generiert werden sollen
        count: Die Anzahl der zu generierenden Fragen (Standard: 10)
        analysis: Eine optionale Analyse des Inhalts (Haupttopic und Subtopics)
        language: Die Sprache der zu generierenden Fragen (Standard: Englisch)
        
    Returns:
        list: Die generierten Fragen
    """
    # Initialisiere den OpenAI-Client
    client = OpenAI(api_key=current_app.config.get('OPENAI_API_KEY'))
    
    # Hole die Topics aus der Analyse
    main_topic = "General Knowledge"
    subtopics = []
    
    if analysis:
        main_topic = analysis.get('main_topic', main_topic)
        subtopics = [s.get('name', '') for s in analysis.get('subtopics', [])]
    
    # Bereite den Prompt vor
    prompt = _build_question_generation_prompt(content, count, main_topic, subtopics, language)
    
    try:
        # Generiere Fragen mit OpenAI
        response = query_chatgpt(prompt, client)
        logger.info(f"Generated questions with OpenAI response of length: {len(response)}")
        
        # Verarbeite die Antwort und extrahiere die Fragen
        questions = _parse_openai_response(response)
        
        # Stelle sicher, dass wir die gewünschte Anzahl an Fragen haben
        if len(questions) < count:
            logger.warning(f"OpenAI generated only {len(questions)} questions, requested {count}. Generating fallback questions.")
            fallback_questions = generate_fallback_questions(analysis, count - len(questions), [], language)
            questions.extend(fallback_questions)
        
        # Begrenze auf die gewünschte Anzahl
        return questions[:count]
    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        # Fallback zu generierten Fragen bei Fehlern
        return generate_fallback_questions(analysis, count, [], language)

def generate_additional_questions(content, client, analysis, existing_questions, count=3, language='en', session_id=None, function_name=None):
    """
    Generiert zusätzliche Fragen zu bereits existierenden Fragen.
    
    Args:
        content: Der Inhalt, auf dessen Basis Fragen generiert werden sollen
        client: Der OpenAI-Client
        analysis: Eine Analyse des Inhalts (Haupttopic und Subtopics)
        existing_questions: Bereits existierende Fragen
        count: Die Anzahl der zu generierenden Fragen (Standard: 3)
        language: Die Sprache der zu generierenden Fragen (Standard: Englisch)
        session_id: Die Sitzungs-ID für Tracking-Zwecke
        function_name: Der Name der aufrufenden Funktion für Tracking-Zwecke
        
    Returns:
        list: Die generierten Fragen
    """
    main_topic = analysis.get('main_topic', 'General Knowledge')
    subtopics = [s.get('name', '') for s in analysis.get('subtopics', [])]
    
    # Bereite den Prompt vor
    prompt = _build_additional_questions_prompt(content, existing_questions, count, main_topic, subtopics, language)
    
    try:
        # Generiere Fragen mit OpenAI
        response = query_chatgpt(prompt, client, session_id=session_id, function_name=function_name)
        logger.info(f"Generated additional questions with OpenAI response of length: {len(response)}")
        
        # Verarbeite die Antwort und extrahiere die Fragen
        questions = _parse_openai_response(response)
        
        # Stelle sicher, dass wir die gewünschte Anzahl an Fragen haben
        if len(questions) < count:
            logger.warning(f"OpenAI generated only {len(questions)} additional questions, requested {count}. Generating fallback questions.")
            fallback_questions = generate_fallback_questions(analysis, count - len(questions), existing_questions, language)
            questions.extend(fallback_questions)
        
        # Begrenze auf die gewünschte Anzahl
        return questions[:count]
    except Exception as e:
        logger.error(f"Error generating additional questions: {str(e)}")
        # Fallback zu generierten Fragen bei Fehlern
        return generate_fallback_questions(analysis, count, existing_questions, language)

def generate_fallback_questions(analysis, count, existing_questions=None, language='en'):
    """
    Generiert einfache Fallback-Fragen, wenn die OpenAI-API fehlschlägt.
    Stellt sicher, dass für jedes Subtopic Fragen erstellt werden.
    Berücksichtigt die erkannte Sprache (Englisch oder Deutsch).
    
    Args:
        analysis: Eine Analyse des Inhalts (Haupttopic und Subtopics)
        count: Die Anzahl der zu generierenden Fragen
        existing_questions: Bereits existierende Fragen (Standard: None)
        language: Die Sprache der zu generierenden Fragen (Standard: Englisch)
        
    Returns:
        list: Die generierten Fallback-Fragen
    """
    main_topic = analysis.get('main_topic', 'General Knowledge')
    subtopics = analysis.get('subtopics', [])
    
    # Extrahiere Subtopic-Namen, wenn subtopics eine Liste von Dictionaries ist
    if subtopics and isinstance(subtopics[0], dict):
        subtopics = [s.get('name', '') for s in subtopics]
    
    if not subtopics or len(subtopics) < 2:
        # Mehr Vielfalt bei den Themen, wenn keine Subtopics vorhanden sind
        if language == 'de':
            subtopics = [
                'Grundkonzepte', 'Definitionen', 'Anwendungen', 'Methoden', 
                'Techniken', 'Vorteile', 'Herausforderungen', 'Beispiele', 
                'Historische Entwicklung', 'Zukunftsperspektiven'
            ]
        else:
            subtopics = [
                'Basic Concepts', 'Definitions', 'Applications', 'Methods',
                'Techniques', 'Advantages', 'Challenges', 'Examples',
                'Historical Development', 'Future Perspectives'
            ]
    
    # Bereite verschiedene Fragetypen vor - spezifischer und abwechslungsreicher
    if language == 'de':
        question_templates = [
            "Welches ist KEIN Merkmal von {topic}?",
            "Was ist der Hauptzweck von {topic}?",
            "Welche Methode wird NICHT bei {topic} verwendet?",
            "Was ist ein wichtiger Vorteil von {topic}?",
            "Welcher Begriff beschreibt {topic} am besten?",
            "Welches ist das primäre Ziel von {topic}?",
            "Welches ist KEINE Anwendung von {topic}?",
            "Was wird in {topic} hauptsächlich analysiert?",
            "Welche der folgenden Aussagen über {topic} ist KORREKT?",
            "Was unterscheidet {topic} von {alternative_topic}?",
            "Welche der folgenden Optionen ist KEINE wichtige Komponente von {topic}?",
            "Welcher Ansatz wird bei {topic} im Kontext von {parent_topic} bevorzugt verwendet?",
            "Was ist ein möglicher Nachteil bei der Anwendung von {topic}?",
            "Welches Prinzip liegt {topic} zugrunde?",
            "In welchem Kontext wird {topic} am häufigsten eingesetzt?"
        ]
        
        contexts = ["Bildung", "Forschung", "Wirtschaft", "Technologie", "Wissenschaft", "Medizin", "Gesellschaft"]
        applications = ["praktische Anwendung", "theoretische Analyse", "konzeptionelle Entwicklung", "strategische Planung"]
        advantages = ["verbesserte Effizienz", "höhere Genauigkeit", "grössere Flexibilität", "bessere Integration"]
        
    else:  # English
        question_templates = [
            "Which is NOT a characteristic of {topic}?",
            "What is the main purpose of {topic}?",
            "Which method is NOT used in {topic}?",
            "What is an important advantage of {topic}?",
            "Which term best describes {topic}?",
            "What is the primary goal of {topic}?",
            "Which is NOT an application of {topic}?",
            "What is primarily analyzed in {topic}?",
            "Which of the following statements about {topic} is CORRECT?",
            "What distinguishes {topic} from {alternative_topic}?",
            "Which of the following options is NOT an important component of {topic}?",
            "Which approach is preferably used in {topic} in the context of {parent_topic}?",
            "What is a potential disadvantage of applying {topic}?",
            "What principle underlies {topic}?",
            "In which context is {topic} most frequently employed?"
        ]
        
        contexts = ["Education", "Research", "Business", "Technology", "Science", "Medicine", "Society"]
        applications = ["practical application", "theoretical analysis", "conceptual development", "strategic planning"]
        advantages = ["improved efficiency", "greater accuracy", "increased flexibility", "better integration"]
    
    # Erstelle eine Menge von vorhandenen Fragen, um Duplikate zu vermeiden
    existing_texts = set()
    if existing_questions:
        existing_texts = {q.get('text', '').lower() for q in existing_questions}
    
    # Generiere Fragen - mit erhöhter Diversität
    questions = []
    topics_to_use = [main_topic] + subtopics
    
    # Generiere bis zu 'count' Fragen, mindestens 3
    min_count = max(count, 3)
    attempts = 0
    max_attempts = min_count * 5  # Erhöhte maximale Versuche
    
    # Stelle sicher, dass für jedes Subtopic mindestens eine Frage erstellt wird
    for topic in topics_to_use:
        if len(questions) >= min_count:
            break
            
        # Wähle randomisierte Elemente für abwechslungsreiche Fragen
        parent_topic = main_topic if topic != main_topic else random.choice(subtopics if subtopics else ["general knowledge" if language == 'en' else "allgemeines Wissen"])
        alternative_topic = random.choice([t for t in topics_to_use if t != topic] or ["other concepts" if language == 'en' else "andere Konzepte"])
        context = random.choice(contexts)
        application = random.choice(applications)
        advantage = random.choice(advantages)
        
        # Wähle zufällig eine Fragenvorlage
        question_template = random.choice(question_templates)
        
        # Erstelle die Frage mit allen Kontextvariablen
        question_text = question_template.format(
            topic=topic, 
            parent_topic=parent_topic,
            alternative_topic=alternative_topic,
            context=context
        )
        
        # Prüfe auf Duplikate
        if question_text.lower() not in existing_texts:
            # Generiere Antwortoptionen je nach Fragetyp
            options = []
            correct_answer = 0
            explanation = ""
            
            if ("KEIN" in question_text or "NICHT" in question_text or "KEINE" in question_text or 
                "NOT" in question_text):
                # Für Negativ-Fragen: 3 richtige und 1 falsche Option
                if language == 'de':
                    correct_parts = [
                        f"Systematische Analyse von {topic}-Konzepten",
                        f"Integration von {topic} in praktische Szenarien",
                        f"Berücksichtigung verschiedener Perspektiven in {topic}"
                    ]
                    incorrect_part = f"Zufällige Anwendung von {topic} ohne strukturierte Methodik"
                    explanation = f"Alle anderen Optionen sind typische Merkmale oder Anwendungen von {topic}."
                else:
                    correct_parts = [
                        f"Systematic analysis of {topic} concepts",
                        f"Integration of {topic} into practical scenarios",
                        f"Consideration of different perspectives in {topic}"
                    ]
                    incorrect_part = f"Random application of {topic} without structured methodology"
                    explanation = f"All other options are typical features or applications of {topic}."
                
                # Mische die Optionen und merke dir die Position der falschen Option
                options = correct_parts + [incorrect_part]
                random.shuffle(options)
                correct_answer = options.index(incorrect_part)
                
            elif "KORREKT" in question_text or "CORRECT" in question_text:
                # Für Fragen nach korrekten Aussagen: 1 richtige und 3 falsche Optionen
                if language == 'de':
                    correct_option = f"{topic} ist ein systematischer Ansatz zur Lösung von Problemen im Bereich {parent_topic}."
                    incorrect_options = [
                        f"{topic} kann nur in theoretischen Kontexten angewendet werden, nicht in der Praxis.",
                        f"{topic} ist ein veraltetes Konzept, das in modernen {context}-Bereichen nicht mehr relevant ist.",
                        f"{topic} widerspricht den Grundprinzipien von {alternative_topic} in jeder Hinsicht."
                    ]
                    explanation = f"Die korrekte Aussage beschreibt die systematische Natur von {topic} und seine Anwendbarkeit in {parent_topic}."
                else:
                    correct_option = f"{topic} is a systematic approach to solving problems in the field of {parent_topic}."
                    incorrect_options = [
                        f"{topic} can only be applied in theoretical contexts, not in practice.",
                        f"{topic} is an outdated concept that is no longer relevant in modern {context} areas.",
                        f"{topic} contradicts the fundamental principles of {alternative_topic} in every respect."
                    ]
                    explanation = f"The correct statement describes the systematic nature of {topic} and its applicability in {parent_topic}."
                
                options = [correct_option] + incorrect_options
                random.shuffle(options)
                correct_answer = options.index(correct_option)
                
            else:
                # Für andere Fragetypen: 1 richtige und 3 falsche Optionen
                if language == 'de':
                    correct_option = f"Systematische Organisation und Anwendung von Wissen über {topic}"
                    incorrect_options = [
                        f"Unsystematische Sammlung von ungeprüften Daten über {topic}",
                        f"Vermeidung jeglicher praktischer Anwendung von {topic}-Konzepten",
                        f"Vereinfachung von {topic} unter Vernachlässigung wichtiger Details"
                    ]
                    explanation = f"Die richtige Antwort beschreibt den systematischen Ansatz, der für {topic} charakteristisch ist."
                else:
                    correct_option = f"Systematic organization and application of knowledge about {topic}"
                    incorrect_options = [
                        f"Unsystematic collection of unverified data about {topic}",
                        f"Avoidance of any practical application of {topic} concepts",
                        f"Simplification of {topic} while neglecting important details"
                    ]
                    explanation = f"The correct answer describes the systematic approach that is characteristic of {topic}."
                
                options = [correct_option] + incorrect_options
                random.shuffle(options)
                correct_answer = options.index(correct_option)
            
            questions.append({
                "text": question_text,
                "options": options,
                "correct": correct_answer,
                "explanation": explanation
            })
            existing_texts.add(question_text.lower())
    
    # Fülle mit weiteren zufälligen Fragen auf, falls noch nicht genug
    while len(questions) < min_count and attempts < max_attempts:
        attempts += 1
        
        # Wähle zufällig ein Thema und Kontextvariablen
        topic = random.choice(topics_to_use)
        parent_topic = main_topic if topic != main_topic else random.choice(subtopics if subtopics else ["general knowledge" if language == 'en' else "allgemeines Wissen"])
        alternative_topic = random.choice([t for t in topics_to_use if t != topic] or ["other concepts" if language == 'en' else "andere Konzepte"])
        context = random.choice(contexts)
        
        # Wähle zufällig eine Fragenvorlage
        question_template = random.choice(question_templates)
        
        # Erstelle die Frage mit allen Kontextvariablen
        question_text = question_template.format(
            topic=topic, 
            parent_topic=parent_topic,
            alternative_topic=alternative_topic,
            context=context
        )
        
        # Prüfe auf Duplikate
        if question_text.lower() not in existing_texts:
            # Generiere Antwortoptionen je nach Fragetyp
            options = []
            correct_answer = 0
            explanation = ""
            
            if ("KEIN" in question_text or "NICHT" in question_text or "KEINE" in question_text or 
                "NOT" in question_text):
                # Für Negativ-Fragen: 3 richtige und 1 falsche Option
                if language == 'de':
                    correct_parts = [
                        f"Strukturierte Analyse von {topic}-Prinzipien",
                        f"Systematische Anwendung von {topic} in {context}",
                        f"Integration von {topic} in {parent_topic}-Kontexte"
                    ]
                    incorrect_part = f"Zufällige Auswahl von {topic}-Methoden ohne klare Kriterien"
                    explanation = f"Die falsche Option beschreibt einen unsystematischen Ansatz, der nicht typisch für {topic} ist."
                else:
                    correct_parts = [
                        f"Structured analysis of {topic} principles",
                        f"Systematic application of {topic} in {context}",
                        f"Integration of {topic} into {parent_topic} contexts"
                    ]
                    incorrect_part = f"Random selection of {topic} methods without clear criteria"
                    explanation = f"The incorrect option describes an unsystematic approach that is not typical for {topic}."
                
                options = correct_parts + [incorrect_part]
                random.shuffle(options)
                correct_answer = options.index(incorrect_part)
                
            else:
                # Für positive Fragen: 1 richtige und 3 falsche Optionen mit Bezug zu konkreten Anwendungen
                if language == 'de':
                    options = [
                        f"Systematische Organisation und Anwendung von {topic} in {context}",  # Die richtige Option
                        f"Zufällige Sammlung von Fakten über {topic} ohne Strukturierung",
                        f"Vermeidung der Integration von {topic} in bestehende {parent_topic}-Prozesse",
                        f"Vereinfachung von {topic} unter Vernachlässigung wichtiger Aspekte"
                    ]
                    explanation = f"Die richtige Antwort beschreibt die systematische und anwendungsorientierte Natur von {topic}."
                else:
                    options = [
                        f"Systematic organization and application of {topic} in {context}",  # The correct option
                        f"Random collection of facts about {topic} without structuring",
                        f"Avoidance of integrating {topic} into existing {parent_topic} processes",
                        f"Simplification of {topic} while neglecting important aspects"
                    ]
                    explanation = f"The correct answer describes the systematic and application-oriented nature of {topic}."
                
                # Mische die Optionen und passe den Index der richtigen Antwort an
                correct_option = options[0]
                random.shuffle(options)
                correct_answer = options.index(correct_option)
            
            questions.append({
                "text": question_text,
                "options": options,
                "correct": correct_answer,
                "explanation": explanation
            })
            existing_texts.add(question_text.lower())
    
    return questions[:count]

def _build_question_generation_prompt(content, count, main_topic, subtopics, language='en'):
    """
    Baut den Prompt für die Generierung von Fragen.
    
    Args:
        content: Der Inhalt, auf dessen Basis Fragen generiert werden sollen
        count: Die Anzahl der zu generierenden Fragen
        main_topic: Das Hauptthema
        subtopics: Die Unterthemen
        language: Die Sprache der zu generierenden Fragen (Standard: Englisch)
        
    Returns:
        str: Der generierte Prompt
    """
    # Kürze langen Inhalt
    if len(content) > 8000:
        content = content[:7800] + "...\n[Content truncated]"
    
    subtopics_str = ", ".join(subtopics) if subtopics else "None"
    
    if language == 'de':
        return f"""
        Generiere {count} Multiple-Choice-Fragen mit jeweils 4 Antwortmöglichkeiten, basierend auf folgendem Text:
        
        ```
        {content}
        ```
        
        Hauptthema: {main_topic}
        Unterthemen: {subtopics_str}
        
        Für jede Frage:
        1. Formuliere eine klare und spezifische Frage.
        2. Stelle 4 mögliche Antworten bereit (eine richtige und drei falsche).
        3. Gib den Index der richtigen Antwort an (0-3).
        4. Füge eine kurze Erklärung hinzu, warum diese Antwort korrekt ist.
        
        Formatiere die Ausgabe als JSON-Array im folgenden Format:
        [
          {{
            "text": "Fragetext",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 0,  // Index der richtigen Antwort (0-3)
            "explanation": "Erklärung, warum diese Antwort richtig ist"
          }},
          // Weitere Fragen...
        ]
        
        Achte auf folgende Anforderungen:
        - Die Fragen sollten unterschiedliche Aspekte des Textes abdecken
        - Die Antwortoptionen sollten plausibel und nicht zu offensichtlich sein
        - Mindestens 2 Fragen sollten sich auf die Unterthemen beziehen
        - Die Fragen sollten verschiedene kognitive Niveaus ansprechen (Wissen, Verständnis, Anwendung)
        - Stelle sicher, dass die Antwortoptionen vergleichbare Länge haben
        - Verwende korrekte deutsche Grammatik und Rechtschreibung
        """
    else:
        return f"""
        Generate {count} multiple-choice questions with 4 answer options each, based on the following text:
        
        ```
        {content}
        ```
        
        Main topic: {main_topic}
        Subtopics: {subtopics_str}
        
        For each question:
        1. Formulate a clear and specific question.
        2. Provide 4 possible answers (one correct and three incorrect).
        3. Indicate the index of the correct answer (0-3).
        4. Add a brief explanation of why this answer is correct.
        
        Format the output as a JSON array with the following structure:
        [
          {{
            "text": "Question text",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 0,  // Index of the correct answer (0-3)
            "explanation": "Explanation of why this answer is correct"
          }},
          // More questions...
        ]
        
        Pay attention to the following requirements:
        - Questions should cover different aspects of the text
        - Answer options should be plausible and not too obvious
        - At least 2 questions should relate to the subtopics
        - Questions should address different cognitive levels (knowledge, comprehension, application)
        - Ensure that answer options have comparable length
        - Use correct English grammar and spelling
        """

def _build_additional_questions_prompt(content, existing_questions, count, main_topic, subtopics, language='en'):
    """
    Baut den Prompt für die Generierung zusätzlicher Fragen.
    
    Args:
        content: Der Inhalt, auf dessen Basis Fragen generiert werden sollen
        existing_questions: Bereits existierende Fragen
        count: Die Anzahl der zusätzlich zu generierenden Fragen
        main_topic: Das Hauptthema
        subtopics: Die Unterthemen
        language: Die Sprache der zu generierenden Fragen (Standard: Englisch)
        
    Returns:
        str: Der generierte Prompt
    """
    # Kürze langen Inhalt
    if len(content) > 6000:
        content = content[:5800] + "...\n[Content truncated]"
    
    # Formatiere existierende Fragen
    existing_questions_text = ""
    for i, q in enumerate(existing_questions[:5]):  # Begrenzt auf maximal 5 Beispielfragen
        existing_questions_text += f"{i+1}. {q.get('text', '')}\n"
    
    subtopics_str = ", ".join(subtopics) if subtopics else "None"
    
    if language == 'de':
        return f"""
        Generiere {count} NEUE Multiple-Choice-Fragen mit jeweils 4 Antwortmöglichkeiten, basierend auf folgendem Text:
        
        ```
        {content}
        ```
        
        Hauptthema: {main_topic}
        Unterthemen: {subtopics_str}
        
        Bereits existierende Fragen (DIESE NICHT WIEDERHOLEN):
        {existing_questions_text}
        
        Für jede NEUE Frage:
        1. Formuliere eine klare und spezifische Frage, die sich von den existierenden unterscheidet.
        2. Stelle 4 mögliche Antworten bereit (eine richtige und drei falsche).
        3. Gib den Index der richtigen Antwort an (0-3).
        4. Füge eine kurze Erklärung hinzu, warum diese Antwort korrekt ist.
        
        Formatiere die Ausgabe als JSON-Array im folgenden Format:
        [
          {{
            "text": "Fragetext",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 0,  // Index der richtigen Antwort (0-3)
            "explanation": "Erklärung, warum diese Antwort richtig ist"
          }},
          // Weitere Fragen...
        ]
        
        Achte auf folgende Anforderungen:
        - Die Fragen MÜSSEN sich von den existierenden unterscheiden
        - Die Fragen sollten unterschiedliche Aspekte des Textes abdecken
        - Die Antwortoptionen sollten plausibel und nicht zu offensichtlich sein
        - Die Fragen sollten verschiedene kognitive Niveaus ansprechen (Wissen, Verständnis, Anwendung)
        - Stelle sicher, dass die Antwortoptionen vergleichbare Länge haben
        - Verwende korrekte deutsche Grammatik und Rechtschreibung
        """
    else:
        return f"""
        Generate {count} NEW multiple-choice questions with 4 answer options each, based on the following text:
        
        ```
        {content}
        ```
        
        Main topic: {main_topic}
        Subtopics: {subtopics_str}
        
        Existing questions (DO NOT REPEAT THESE):
        {existing_questions_text}
        
        For each NEW question:
        1. Formulate a clear and specific question that differs from the existing ones.
        2. Provide 4 possible answers (one correct and three incorrect).
        3. Indicate the index of the correct answer (0-3).
        4. Add a brief explanation of why this answer is correct.
        
        Format the output as a JSON array with the following structure:
        [
          {{
            "text": "Question text",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 0,  // Index of the correct answer (0-3)
            "explanation": "Explanation of why this answer is correct"
          }},
          // More questions...
        ]
        
        Pay attention to the following requirements:
        - Questions MUST differ from the existing ones
        - Questions should cover different aspects of the text
        - Answer options should be plausible and not too obvious
        - Questions should address different cognitive levels (knowledge, comprehension, application)
        - Ensure that answer options have comparable length
        - Use correct English grammar and spelling
        """

def _parse_openai_response(response):
    """
    Parst die Antwort der OpenAI-API und extrahiert die generierten Fragen.
    
    Args:
        response: Die Antwort der OpenAI-API
        
    Returns:
        list: Die extrahierten Fragen
    """
    try:
        # Suche nach JSON-Array in der Antwort
        start_idx = response.find('[')
        end_idx = response.rfind(']')
        
        if start_idx == -1 or end_idx == -1:
            logger.warning("Could not find JSON array in OpenAI response")
            # Versuche, einzelne Fragen zu extrahieren
            return []
        
        # Extrahiere und parse das JSON-Array
        json_str = response[start_idx:end_idx+1]
        questions = json.loads(json_str)
        
        # Validiere und normalisiere die Fragen
        valid_questions = []
        for question in questions:
            if "text" in question and "options" in question and "correct" in question:
                # Stelle sicher, dass das correct-Feld ein Integer ist
                try:
                    question["correct"] = int(question["correct"])
                except (ValueError, TypeError):
                    # Falls 'correct' kein Integer ist, setze es auf 0
                    question["correct"] = 0
                
                # Stelle sicher, dass es genau 4 Optionen gibt
                if len(question["options"]) != 4:
                    # Passe die Anzahl der Optionen an
                    if len(question["options"]) < 4:
                        question["options"].extend(["Option"] * (4 - len(question["options"])))
                    else:
                        question["options"] = question["options"][:4]
                
                # Stelle sicher, dass correct im gültigen Bereich liegt
                if question["correct"] < 0 or question["correct"] >= len(question["options"]):
                    question["correct"] = 0
                
                valid_questions.append(question)
        
        return valid_questions
    except Exception as e:
        logger.error(f"Error parsing OpenAI response: {str(e)}")
        return [] 