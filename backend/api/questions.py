from flask import request, jsonify, current_app, g
from . import api_bp
from .utils import generate_additional_questions, detect_language
from core.models import db, Upload, Question, UserActivity, Topic, User
from marshmallow import Schema, fields, ValidationError
import logging
from api.token_tracking import check_credits_available, calculate_token_cost, deduct_credits
import tiktoken
import json
from .auth import token_required
from openai import OpenAI
import os

logger = logging.getLogger(__name__)

# CORS-Konfiguration für alle Endpoints
CORS_CONFIG = {
    "supports_credentials": True,
    "origins": os.environ.get('CORS_ORIGINS', '*'),
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}

class QuestionRequestSchema(Schema):
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)

@api_bp.route('/generate-more-questions', methods=['POST', 'OPTIONS'])
def generate_more_questions():
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung für nicht-OPTIONS Anfragen
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
    data = request.get_json()
    if not data or 'session_id' not in data:
        return jsonify({'error': 'Session-ID erforderlich', 'success': False}), 400
    
    session_id = data['session_id']
    count = data.get('count', 3)  # Standardmäßig 3 neue Fragen
    
    # Extrahiere den Timestamp, falls vorhanden, um Caching zu vermeiden
    timestamp = data.get('timestamp', '')
    logger.info(f"Generating questions with timestamp: {timestamp}")
    
    # Lade die Sitzungsdaten
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({'error': 'Sitzung nicht gefunden', 'success': False}), 404
    
    # Lade die vorhandenen Fragen
    existing_questions = Question.query.filter_by(upload_id=upload.id).all()
    existing_questions_data = [
        {
            'text': q.text, 
            'options': q.options, 
            'correct': q.correct_answer,
            'explanation': q.explanation
        } 
        for q in existing_questions
    ]
    
    # Lade die Analyse
    main_topic = "Unbekanntes Thema"
    subtopics = []
    
    # Prüfe auf ein vorhandenes Hauptthema
    main_topic_obj = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
    if main_topic_obj:
        main_topic = main_topic_obj.name
    
    # Lade Subtopics
    subtopic_objs = Topic.query.filter_by(upload_id=upload.id, is_main_topic=False, parent_id=None).all()
    subtopics = [subtopic.name for subtopic in subtopic_objs]
    
    # Erstelle eine Analyse-Zusammenfassung
    analysis = {
        'main_topic': main_topic,
        'subtopics': [{'name': subtopic} for subtopic in subtopics]
    }
    
    try:
        # Berechne geschätzte Kosten für diesen Aufruf
        # Wir schätzen Tokens basierend auf vorhandenen Fragen und dem gewünschten Count
        estimated_input_tokens = 1000 + len(existing_questions) * 100
        estimated_output_tokens = count * 200  # Grobe Schätzung
        
        # Berechne die Kosten
        estimated_cost = calculate_token_cost(estimated_input_tokens, estimated_output_tokens)
        
        # Prüfe, ob Benutzer genug Credits hat
        if not check_credits_available(estimated_cost):
            return jsonify({
                'error': {
                    'message': f'Nicht genügend Credits. Benötigt: {estimated_cost} Credits für diese Anfrage.',
                    'credits_required': estimated_cost,
                    'credits_available': g.user.credits if hasattr(g, 'user') and g.user else 0
                },
                'error_type': 'insufficient_credits',
                'success': False
            }), 402
        
        # Berechne tatsächlich abzuziehende Credits nach API-Aufruf
        # Diese werden während der API-Generierung berechnet und abgezogen
        
        # Initialize OpenAI client
        openai_api_key = current_app.config.get('OPENAI_API_KEY')
        client = OpenAI(api_key=openai_api_key)
        
        # Generiere neue Fragen
        new_questions = generate_additional_questions(
            upload.content,
            client,
            analysis,
            existing_questions_data,
            count,
            language='de' if detect_language(upload.content) == 'de' else 'en',
            session_id=session_id,  # Übergebe session_id für Token-Tracking
            function_name="generate_more_questions"  # Definiere die Funktion für das Tracking
        )
        
        # Speichere neue Fragen in der Datenbank
        for question_data in new_questions:
            question = Question(
                upload_id=upload.id,
                text=question_data['text'],
                options=question_data['options'],
                correct_answer=question_data['correct'],
                explanation=question_data.get('explanation', '')
            )
            db.session.add(question)
        
        db.session.commit()
        
        # Aktualisiere die Nutzungszeit für diese Sitzung
        upload.last_used_at = db.func.current_timestamp()
        db.session.commit()
        
        # Lade die aktualisierten Fragen
        all_questions = Question.query.filter_by(upload_id=upload.id).all()
        questions_data = [
            {
                'id': q.id, 
                'text': q.text, 
                'options': q.options, 
                'correct': q.correct_answer,
                'explanation': q.explanation
            } 
            for q in all_questions
        ]
        
        # Erstelle eine UserActivity-Eintrag für diese Aktion
        if hasattr(g, 'user') and g.user:
            user_activity = UserActivity(
                user_id=g.user.id,
                activity_type='question',
                title=f'Generierte {len(new_questions)} zusätzliche Testfragen',
                main_topic=main_topic,
                subtopics=subtopics,
                session_id=session_id,
                details={
                    'count': len(new_questions),
                    'total_count': len(questions_data)
                }
            )
            db.session.add(user_activity)
            db.session.commit()
        
        # Rückgabe der erfolgreich generierten Fragen
        return jsonify({
            'success': True,
            'message': f'{len(new_questions)} neue Testfragen wurden erfolgreich generiert.',
            'questions': questions_data,  # Direkt auf der ersten Ebene für ältere Client-Versionen
            'data': {
                'questions': questions_data
            },
            'credits_available': g.user.credits if hasattr(g, 'user') and g.user else 0
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Generieren von Testfragen: {str(e)}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

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

@api_bp.route('/questions/generate/<session_id>', methods=['POST', 'OPTIONS'])
def generate_questions_route(session_id):
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        response = jsonify({"success": True})
        return response
        
    # Authentifizierung für nicht-OPTIONS Anfragen
    auth_decorator = token_required(lambda: None)
    auth_result = auth_decorator()
    if auth_result is not None:
        return auth_result
    
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
    
    # Anpassung der Output-Token-Schätzung basierend auf der Eingabegröße
    if estimated_prompt_tokens < 100:
        estimated_output_tokens = 200  # Minimale Ausgabe für winzige Dokumente
    elif estimated_prompt_tokens < 500:
        estimated_output_tokens = 500  # Reduzierte Ausgabe für kleine Dokumente
    else:
        estimated_output_tokens = 3000  # Geschätzte Ausgabe für Fragen
    
    # Berechne die ungefähren Kosten
    content_tokens = count_tokens(upload.content)
    estimated_cost = calculate_token_cost(estimated_prompt_tokens, estimated_output_tokens, document_tokens=content_tokens)
    
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