from flask import request, jsonify, current_app, g
from . import api_bp
from .utils import generate_additional_questions, detect_language
from models import db, Upload, Question, UserActivity, Topic, User
from marshmallow import Schema, fields, ValidationError
import logging
from .auth import token_required
from api.credit_service import check_credits_available, calculate_token_cost, deduct_credits
import tiktoken
import json

logger = logging.getLogger(__name__)

class QuestionRequestSchema(Schema):
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)

@api_bp.route('/generate-more-questions', methods=['POST'])
@token_required
def generate_more_questions():
    try:
        data = QuestionRequestSchema().load(request.json)
    except ValidationError as e:
        return jsonify({"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(e.messages)}}), 400
    
    session_id = data['session_id']
    count = max(data['count'], 3)  # Mindestens 3 Fragen generieren
    logger.info(f"Generating {count} more questions for session_id: {session_id}")
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    # Import der Credit-Service-Funktionen
    from api.credit_service import check_credits_available, calculate_token_cost, deduct_credits
    from flask import g
    import tiktoken
    
    # Helper-Funktion für die Tokenzählung
    def count_tokens(text, model="gpt-4o"):
        """Zählt die Anzahl der Tokens in einem Text für ein bestimmtes Modell"""
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except:
            # Fallback: Ungefähre Schätzung (1 Token ≈ 4 Zeichen)
            return len(text) // 4
    
    # Hole alle bestehenden Fragen für diese Upload-ID
    existing_questions = [
        {"text": q.text, "options": q.options, "correct": q.correct_answer, "explanation": q.explanation}
        for q in Question.query.filter_by(upload_id=upload.id).all()
    ]
    logger.info(f"Found {len(existing_questions)} existing questions for session_id: {session_id}")
    
    # Initialisiere den OpenAI-Client
    from openai import OpenAI
    client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    
    # Ermittle die Sprache und analysiere den Inhalt
    language = detect_language(upload.content)
    main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    
    # Fallback, falls kein Hauptthema gefunden wird
    main_topic_name = "Unknown Topic"
    subtopics = []
    
    if main_topic:
        main_topic_name = main_topic.name
        subtopics = [topic.name for topic in Topic.query.filter_by(upload_id=upload.id, is_main_topic=False).all()]
    
    analysis = {
        "main_topic": main_topic_name,
        "subtopics": subtopics
    }
    logger.info(f"Analysis for session_id {session_id}: Main topic={analysis['main_topic']}, Subtopics={analysis['subtopics']}")
    
    # Schätze die maximalen Tokenkosten für diesen Aufruf
    # Dies ist nur eine Schätzung für die Prüfung vor der Generierung
    # Fragen haben mehr Token als Flashcards wegen Optionen und Erklärungen
    estimated_input_tokens = 2000 + (count * 200)  # Kontext + Prompt + Eingabe pro Frage
    estimated_output_tokens = count * 300  # ca. 300 Tokens Ausgabe pro Frage
    max_estimated_cost = calculate_token_cost(estimated_input_tokens, estimated_output_tokens)
    
    # Verdopple die geschätzten Kosten für den Gewinn
    max_estimated_cost = max_estimated_cost * 2
    
    # Überprüfe, ob genügend Credits vorhanden sind
    if not check_credits_available(max_estimated_cost):
        # Hole den aktuellen Benutzer und seine Credits
        user = User.query.get(g.user.id)
        current_credits = user.credits if user else 0
        
        return jsonify({
            "success": False,
            "error": {
                "code": "INSUFFICIENT_CREDITS",
                "message": f"Nicht genügend Credits. Sie benötigen maximal {max_estimated_cost} Credits für {count} neue Testfragen, haben aber nur {current_credits} Credits.",
                "credits_required": max_estimated_cost,
                "credits_available": current_credits
            }
        }), 402  # 402 Payment Required
    
    # Die Anzahl der zu generierenden Fragen erhöhen, um sicherzustellen, dass nach der Duplikatfilterung 
    # noch genügend übrig bleiben
    generation_count = max(count * 2, 10)  # Erhöhte Anzahl zur Generation
    
    try:
        # Generiere den Prompt für die Fragen
        prompt_template = f"""
        Ich benötige {generation_count} ZUSÄTZLICHE, EINZIGARTIGE Testfragen mit Multiple-Choice-Optionen, die sich VÖLLIG von den vorhandenen unterscheiden.
        
        Hauptthema: {analysis['main_topic']}
        Unterthemen: {', '.join(analysis['subtopics'])}
        
        VORHANDENE TESTFRAGEN (DIESE NICHT DUPLIZIEREN ODER UMFORMULIEREN):
        """
        
        # Füge die vorhandenen Fragen zum Prompt hinzu
        for i, q in enumerate(existing_questions[:5]):
            options_text = str(q.get('options', []))
            correct_answer = q.get('correct', 0)
            prompt_template += f"\n{i+1}. Frage: {q.get('text', '')}\nOptionen: {options_text}\nRichtige Antwort: {correct_answer}"
        
        # Füge Format-Anforderungen hinzu
        prompt_template += """
        
        FORMATANFORDERUNGEN:
        - Jede Frage sollte einen klaren Fragetext, 4 Optionen und die richtige Antwort haben
        - Die richtige Antwort sollte als Index der Option (0-3) angegeben werden
        - Füge eine kurze Erklärung für die richtige Antwort hinzu
        
        GEBEN SIE NUR DIE FRAGEN IN DIESEM JSON-FORMAT ZURÜCK:
        [
          {
            "text": "Ihre Frage hier",
            "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
            "correct": 0,
            "explanation": "Erklärung, warum Option 1 richtig ist"
          }
        ]
        """
        
        # Zähle die Tokens für den Prompt
        input_tokens = count_tokens(prompt_template)
        
        # Verwende die Funktion aus utils.py für einzigartige, zusätzliche Fragen
        new_questions = generate_additional_questions(
            upload.content,
            client,
            analysis=analysis,
            existing_questions=existing_questions,
            num_to_generate=generation_count,  # Erhöhte Anzahl
            language=language
        )
        
        # Filtere Duplikate basierend auf dem Text
        filtered_questions = [
            q for q in new_questions
            if not any(q['text'].lower() == ex['text'].lower() for ex in existing_questions)
        ]
        
        # Begrenze auf die angeforderte Anzahl
        limited_questions = filtered_questions[:count]
        logger.info(f"Generated {len(filtered_questions)} new questions before limiting to {count}")
        
        # Berechne die tatsächlichen Tokens für die Antwort
        response_text = json.dumps(limited_questions)
        output_tokens = count_tokens(response_text)
        
        # Berechne die tatsächlichen Kosten basierend auf den verwendeten Tokens
        actual_cost = calculate_token_cost(input_tokens, output_tokens)
        
        # Verdopple die tatsächlichen Kosten für den Gewinn
        actual_cost = actual_cost * 2
        
        # Ziehe die Credits vom Benutzer ab
        deduct_credits(g.user.id, actual_cost)
        logger.info(f"Deducted {actual_cost} credits from user {g.user.id} for generating {count} questions")
        
    except Exception as e:
        logger.error(f"Error calling generate_additional_questions: {str(e)}")
        # Generiere einfache Fallback-Fragen, wenn die OpenAI-API fehlschlägt
        filtered_questions = generate_fallback_questions(analysis, generation_count, existing_questions, language)
        logger.info(f"Generated {len(filtered_questions)} fallback questions")
    
    # Überprüfe, ob genug einzigartige Fragen generiert wurden
    if len(filtered_questions) < 3:
        # Wenn nicht genug, generiere weitere Fallback-Fragen
        additional_questions = generate_fallback_questions(
            analysis, 
            max(10, 3 - len(filtered_questions)), 
            existing_questions + filtered_questions,
            language
        )
        filtered_questions.extend(additional_questions)
        logger.info(f"Added {len(additional_questions)} additional fallback questions")
    
    try:
        # Begrenze die Anzahl der zurückgegebenen Fragen auf die angeforderte Anzahl,
        # aber mindestens 3
        final_count = max(count, 3)
        filtered_questions = filtered_questions[:final_count]
        
        # Speichere nur gültige Fragen in der Datenbank
        for q in filtered_questions:
            if q.get('text') and q.get('options') and not q['text'].startswith('Could not generate'):
                question = Question(
                    upload_id=upload.id,
                    text=q['text'],
                    options=q['options'],
                    correct_answer=q.get('correct', 0),
                    explanation=q.get('explanation', '')
                )
                db.session.add(question)
                logger.info(f"Saved question: {q['text']}")
        
        # Begrenze auf 5 Einträge
        existing_activities = UserActivity.query.filter_by(user_id=request.user_id).order_by(UserActivity.timestamp.asc()).all()
        if len(existing_activities) >= 5:
            oldest_activity = existing_activities[0]
            db.session.delete(oldest_activity)
            logger.info(f"Deleted oldest activity: {oldest_activity.id}")
        
        # Logge und speichere Benutzeraktivität
        activity = UserActivity(
            user_id=request.user_id,
            activity_type='test',
            title=f"Generated {len(filtered_questions)} more questions",
            main_topic=analysis['main_topic'],
            subtopics=analysis['subtopics'],
            session_id=session_id,
            details={"count": len(filtered_questions), "session_id": session_id}
        )
        db.session.add(activity)
        logger.info(f"Logged user activity for generating {len(filtered_questions)} questions")
        
        db.session.commit()
        return jsonify({
            "success": True,
            "data": {
                "questions": filtered_questions
            },
            "message": f"Successfully generated {len(filtered_questions)} additional questions"
        }), 200
    except Exception as e:
        logger.error(f"Error saving questions to database for session_id {session_id}: {str(e)}")
        db.session.rollback()
        
        # Wenn der Datenbankfehler auftritt, trotzdem versuchen, Fragen zurückzugeben
        return jsonify({
            "success": True,
            "data": {
                "questions": filtered_questions
            },
            "message": "Questions generated but could not be saved to database"
        }), 200

def generate_fallback_questions(analysis, count, existing_questions, language='en'):
    """
    Generiert einfache Fallback-Fragen, wenn die OpenAI-API fehlschlägt.
    Stellt sicher, dass für jedes Subtopic Fragen erstellt werden.
    Berücksichtigt die erkannte Sprache (Englisch oder Deutsch).
    """
    main_topic = analysis.get('main_topic', 'General Knowledge')
    subtopics = analysis.get('subtopics', [])
    
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
    existing_texts = {q.get('text', '').lower() for q in existing_questions}
    
    # Generiere Fragen - mit erhöhter Diversität
    questions = []
    topics_to_use = [main_topic] + subtopics
    
    # Generiere bis zu 'count' Fragen, mindestens 3
    min_count = max(count, 3)
    attempts = 0
    max_attempts = min_count * 5  # Erhöhte maximale Versuche
    
    import random
    
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
    
    return questions

@api_bp.route('/questions/generate/<session_id>', methods=['POST'])
@token_required
def generate_questions_route(session_id):
    # Parameter aus der Anfrage extrahieren
    count = request.json.get('count', 10)  # Standardmäßig 10 Fragen generieren
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    # Prüfen, ob der Text zu lang ist
    content = upload.content or ""
    content_length = len(content)
    
    if content_length > 100000:
        return jsonify({
            "success": False,
            "error": {
                "code": "CONTENT_TOO_LARGE",
                "message": "Der Text ist zu lang. Bitte versuchen Sie es mit einem kürzeren Text."
            }
        }), 400
        
    # Schätze die Kosten basierend auf der Länge des Inhalts
    estimated_prompt_tokens = min(content_length // 3, 100000)  # Ungefähre Schätzung: 1 Token pro 3 Zeichen
    estimated_output_tokens = 3000  # Geschätzte Ausgabe für Fragen (mehr als Flashcards)
    
    # Berechne die ungefähren Kosten
    estimated_cost = calculate_token_cost(estimated_prompt_tokens, estimated_output_tokens)
    
    # Prüfe, ob der Benutzer genügend Credits hat
    if not check_credits_available(estimated_cost):
        # Hole die aktuellen Credits des Benutzers
        user = User.query.get(g.user.id)
        current_credits = user.credits if user else 0
        
        return jsonify({
            "success": False,
            "error": {
                "code": "INSUFFICIENT_CREDITS",
                "message": f"Nicht genügend Credits. Sie benötigen {estimated_cost} Credits für diese Anfrage, haben aber nur {current_credits} Credits.",
                "credits_required": estimated_cost,
                "credits_available": current_credits
            }
        }), 402