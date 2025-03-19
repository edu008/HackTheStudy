from flask import request, jsonify, current_app
from . import api_bp
from .utils import generate_additional_flashcards, detect_language
from models import db, Upload, Flashcard, UserActivity, Topic
from marshmallow import Schema, fields, ValidationError
import logging
from .auth import token_required

logger = logging.getLogger(__name__)

class FlashcardRequestSchema(Schema):
    session_id = fields.Str(required=True)
    count = fields.Int(required=True, validate=lambda n: n > 0)

@api_bp.route('/generate-more-flashcards', methods=['POST'])
@token_required
def generate_more_flashcards():
    try:
        data = FlashcardRequestSchema().load(request.json)
    except ValidationError as e:
        return jsonify({"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(e.messages)}}), 400
    
    session_id = data['session_id']
    count = max(data['count'], 3)  # Mindestens 3 Flashcards generieren
    logger.info(f"Generating {count} more flashcards for session_id: {session_id}")
    
    upload = Upload.query.filter_by(session_id=session_id).first()
    if not upload:
        return jsonify({"success": False, "error": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}}), 404
    
    # Hole alle bestehenden Flashcards für diese Upload-ID
    existing_flashcards = [
        {"question": f.question, "answer": f.answer}
        for f in Flashcard.query.filter_by(upload_id=upload.id).all()
    ]
    logger.info(f"Found {len(existing_flashcards)} existing flashcards for session_id: {session_id}")
    
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
    
    # Die Anzahl der zu generierenden Flashcards erhöhen, um sicherzustellen, dass nach der Duplikatfilterung 
    # noch genügend übrig bleiben
    generation_count = max(count * 2, 10)  # Erhöhte Anzahl zur Generation
    
    try:
        # Verwende die Funktion aus utils.py für einzigartige, zusätzliche Flashcards
        new_flashcards = generate_additional_flashcards(
            upload.content,
            client,
            analysis=analysis,
            existing_flashcards=existing_flashcards,
            num_to_generate=generation_count,  # Erhöhte Anzahl
            language=language
        )
        
        # Filtere Duplikate basierend auf der Frage
        filtered_flashcards = [
            f for f in new_flashcards
            if not any(f['question'].lower() == ex['question'].lower() for ex in existing_flashcards)
        ]
        logger.info(f"Generated {len(filtered_flashcards)} new flashcards before limiting to {count}")
        
    except Exception as e:
        logger.error(f"Error calling generate_additional_flashcards: {str(e)}")
        # Generiere einfache Fallback-Flashcards, wenn die OpenAI-API fehlschlägt
        filtered_flashcards = generate_fallback_flashcards(analysis, generation_count, existing_flashcards, language)
        logger.info(f"Generated {len(filtered_flashcards)} fallback flashcards")
    
    # Überprüfe, ob genug einzigartige Flashcards generiert wurden
    if len(filtered_flashcards) < 3:
        # Wenn nicht genug, generiere weitere Fallback-Flashcards
        additional_flashcards = generate_fallback_flashcards(
            analysis, 
            max(10, 3 - len(filtered_flashcards)), 
            existing_flashcards + filtered_flashcards,
            language
        )
        filtered_flashcards.extend(additional_flashcards)
        logger.info(f"Added {len(additional_flashcards)} additional fallback flashcards")
    
    try:
        # Begrenze die Anzahl der zurückgegebenen Flashcards auf die angeforderte Anzahl,
        # aber mindestens 3
        final_count = max(count, 3)
        filtered_flashcards = filtered_flashcards[:final_count]
        
        # Speichere nur gültige Flashcards in der Datenbank
        for f in filtered_flashcards:
            if f.get('question') and f.get('answer') and not f['question'].startswith('Could not generate'):
                flashcard = Flashcard(
                    upload_id=upload.id,
                    question=f['question'],
                    answer=f['answer']
                )
                db.session.add(flashcard)
                logger.info(f"Saved flashcard: {f['question']}")
        
        # Begrenze auf 5 Einträge
        existing_activities = UserActivity.query.filter_by(user_id=request.user_id).order_by(UserActivity.timestamp.asc()).all()
        if len(existing_activities) >= 5:
            oldest_activity = existing_activities[0]
            db.session.delete(oldest_activity)
            logger.info(f"Deleted oldest activity: {oldest_activity.id}")
        
        # Logge und speichere Benutzeraktivität
        activity = UserActivity(
            user_id=request.user_id,
            activity_type='flashcard',
            title=f"Generated {len(filtered_flashcards)} more flashcards",
            main_topic=analysis['main_topic'],
            subtopics=analysis['subtopics'],
            session_id=session_id,
            details={"count": len(filtered_flashcards), "session_id": session_id}
        )
        db.session.add(activity)
        logger.info(f"Logged user activity for generating {len(filtered_flashcards)} flashcards")
        
        db.session.commit()
        return jsonify({
            "success": True,
            "data": {
                "flashcards": filtered_flashcards
            },
            "message": f"Successfully generated {len(filtered_flashcards)} additional flashcards"
        }), 200
    except Exception as e:
        logger.error(f"Error saving flashcards to database for session_id {session_id}: {str(e)}")
        db.session.rollback()
        
        # Wenn der Datenbankfehler auftritt, trotzdem versuchen, Flashcards zurückzugeben
        return jsonify({
            "success": True,
            "data": {
                "flashcards": filtered_flashcards
            },
            "message": "Flashcards generated but could not be saved to database"
        }), 200

def generate_fallback_flashcards(analysis, count, existing_flashcards, language='en'):
    """
    Generiert einfache Fallback-Flashcards, wenn die OpenAI-API fehlschlägt.
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
            "Was sind die Hauptmerkmale von {topic}?",
            "Wie definiert man {topic} im akademischen Kontext?",
            "Warum ist {topic} wichtig für das Verständnis von {parent_topic}?",
            "Welche praktischen Anwendungen hat {topic} in der realen Welt?",
            "Erkläre das Konzept von {topic} mit eigenen Worten.",
            "Wie unterscheidet sich {topic} von {alternative_topic}?",
            "Was sind drei konkrete Beispiele für {topic}?",
            "Welche Methoden werden bei der Analyse von {topic} eingesetzt?",
            "Wie hat sich das Verständnis von {topic} im Laufe der Zeit entwickelt?",
            "Welche Vor- und Nachteile bietet der Einsatz von {topic}?",
            "Wie kann man {topic} in {context} praktisch umsetzen?",
            "Was sind die wichtigsten Prinzipien bei der Anwendung von {topic}?",
            "Inwiefern beeinflusst {topic} die Entwicklung von {related_field}?",
            "Welche ethischen Überlegungen sind bei {topic} zu beachten?",
            "Wie kann man die Wirksamkeit von {topic} messen oder bewerten?",
        ]
        
        answer_templates = [
            "Die Hauptmerkmale von {topic} sind die strukturierte Organisation von Wissen, die Anwendbarkeit auf verschiedene Szenarien und die Möglichkeit, komplexe Sachverhalte zu vermitteln.",
            "{topic} wird im akademischen Kontext definiert als systematischer Ansatz zur Lösung von Problemen durch Analyse, Synthese und Anwendung von Wissen in {parent_topic}.",
            "{topic} ist wichtig für das Verständnis von {parent_topic}, weil es fundamentale Konzepte bietet, die zum tieferen Verständnis beitragen und praktische Anwendungen ermöglichen.",
            "Praktische Anwendungen von {topic} finden sich in Bereichen wie {context}, wo es zur Lösung komplexer Probleme und zur Optimierung von Prozessen eingesetzt wird.",
            "Das Konzept von {topic} umfasst die systematische Anordnung von Informationen, die kritische Analyse und die praktische Anwendung von Wissen, um bestimmte Ziele zu erreichen.",
            "{topic} unterscheidet sich von {alternative_topic} durch seinen spezifischen Fokus auf praktische Anwendungen, während {alternative_topic} eher theoretische Aspekte betont.",
            "Konkrete Beispiele für {topic} sind der Einsatz in Bildungseinrichtungen zur Verbesserung des Lernens, die Anwendung in Unternehmen zur Prozessoptimierung und die Nutzung in der Forschung zur Generierung neuer Erkenntnisse.",
            "Bei der Analyse von {topic} werden Methoden wie systematische Beobachtung, vergleichende Untersuchungen, quantitative Messungen und qualitative Bewertungen eingesetzt.",
            "Das Verständnis von {topic} hat sich von einem ursprünglich theoretischen Konzept zu einem praktisch anwendbaren Ansatz entwickelt, der heute in vielen Bereichen eingesetzt wird.",
            "Vorteile des Einsatzes von {topic} sind die verbesserte Effizienz und Effektivität, während Nachteile den anfänglichen Lernaufwand und mögliche Anpassungsschwierigkeiten umfassen.",
            "Die praktische Umsetzung von {topic} in {context} erfordert eine sorgfältige Planung, die Einbeziehung aller Beteiligten und eine kontinuierliche Evaluation der Ergebnisse.",
            "Die wichtigsten Prinzipien bei der Anwendung von {topic} sind Systematik, Konsistenz, Anpassungsfähigkeit und eine kontinuierliche Verbesserung basierend auf Feedback.",
            "{topic} beeinflusst die Entwicklung von {related_field} durch die Bereitstellung von strukturierten Methoden, innovativen Ansätzen und neuen Perspektiven.",
            "Bei {topic} sind ethische Überlegungen wie Fairness, Transparenz, Respekt für die Autonomie und die Berücksichtigung unterschiedlicher Perspektiven zu beachten.",
            "Die Wirksamkeit von {topic} kann durch quantitative Messungen wie Leistungsindikatoren, qualitative Bewertungen wie Nutzerfeedback und langfristige Erfolgsanalysen gemessen werden."
        ]
        
        contexts = ["Bildung", "Forschung", "Wirtschaft", "Technologie", "Wissenschaft", "Medizin", "Gesellschaft"]
        related_fields = ["Informatik", "Wirtschaft", "Psychologie", "Naturwissenschaften", "Ingenieurwesen", "Sozialwissenschaften"]
    
    else:  # English
        question_templates = [
            "What are the main characteristics of {topic}?",
            "How is {topic} defined in an academic context?",
            "Why is {topic} important for understanding {parent_topic}?",
            "What practical applications does {topic} have in the real world?",
            "Explain the concept of {topic} in your own words.",
            "How does {topic} differ from {alternative_topic}?",
            "What are three concrete examples of {topic}?",
            "What methods are used in the analysis of {topic}?",
            "How has the understanding of {topic} evolved over time?",
            "What are the advantages and disadvantages of using {topic}?",
            "How can {topic} be practically implemented in {context}?",
            "What are the key principles in the application of {topic}?",
            "How does {topic} influence the development of {related_field}?",
            "What ethical considerations should be observed with {topic}?",
            "How can the effectiveness of {topic} be measured or evaluated?",
        ]
        
        answer_templates = [
            "The main characteristics of {topic} include structured organization of knowledge, applicability to various scenarios, and the ability to convey complex matters.",
            "{topic} is defined in academic contexts as a systematic approach to problem-solving through analysis, synthesis, and application of knowledge in {parent_topic}.",
            "{topic} is important for understanding {parent_topic} because it provides fundamental concepts that contribute to deeper understanding and enables practical applications.",
            "Practical applications of {topic} can be found in areas such as {context}, where it is used to solve complex problems and optimize processes.",
            "The concept of {topic} encompasses the systematic arrangement of information, critical analysis, and practical application of knowledge to achieve specific goals.",
            "{topic} differs from {alternative_topic} through its specific focus on practical applications, while {alternative_topic} emphasizes theoretical aspects.",
            "Concrete examples of {topic} include its use in educational institutions to improve learning, its application in businesses for process optimization, and its use in research to generate new insights.",
            "In the analysis of {topic}, methods such as systematic observation, comparative studies, quantitative measurements, and qualitative assessments are employed.",
            "The understanding of {topic} has evolved from an originally theoretical concept to a practically applicable approach that is used in many fields today.",
            "Advantages of using {topic} include improved efficiency and effectiveness, while disadvantages include the initial learning effort and potential adaptation difficulties.",
            "The practical implementation of {topic} in {context} requires careful planning, involvement of all stakeholders, and continuous evaluation of results.",
            "The most important principles in the application of {topic} are systematicity, consistency, adaptability, and continuous improvement based on feedback.",
            "{topic} influences the development of {related_field} by providing structured methods, innovative approaches, and new perspectives.",
            "In {topic}, ethical considerations such as fairness, transparency, respect for autonomy, and consideration of different perspectives should be observed.",
            "The effectiveness of {topic} can be measured through quantitative metrics like performance indicators, qualitative assessments like user feedback, and long-term success analyses."
        ]
        
        contexts = ["Education", "Research", "Business", "Technology", "Science", "Medicine", "Society"]
        related_fields = ["Computer Science", "Economics", "Psychology", "Natural Sciences", "Engineering", "Social Sciences"]
    
    # Generiere Flashcards - mit erhöhter Diversität
    flashcards = []
    # Stellen sicher, dass alle Subtopics verwendet werden
    topics_to_use = [main_topic] + subtopics
    
    # Erstelle eine Menge von vorhandenen Fragen, um Duplikate zu vermeiden
    existing_questions = {f.get('question', '').lower() for f in existing_flashcards}
    
    # Generiere bis zu 'count' Flashcards, immer mindestens 3
    min_count = max(count, 3)
    attempts = 0
    max_attempts = min_count * 5  # Erhöhte maximale Versuche
    
    import random
    
    # Stelle sicher, dass für jedes Subtopic mindestens eine Flashcard erstellt wird
    for topic in topics_to_use:
        if len(flashcards) >= min_count:
            break
            
        # Wähle randomisierte Elemente für abwechslungsreiche Fragen
        parent_topic = main_topic if topic != main_topic else random.choice(subtopics if subtopics else ["general knowledge" if language == 'en' else "allgemeines Wissen"])
        alternative_topic = random.choice([t for t in topics_to_use if t != topic] or ["other concepts" if language == 'en' else "andere Konzepte"])
        context = random.choice(contexts)
        related_field = random.choice(related_fields)
        
        # Wähle zufällig eine Vorlage
        question_template = random.choice(question_templates)
        answer_template = random.choice(answer_templates)
        
        # Erstelle die Frage mit allen Kontextvariablen
        question = question_template.format(
            topic=topic, 
            parent_topic=parent_topic,
            alternative_topic=alternative_topic,
            context=context,
            related_field=related_field
        )
        
        # Erstelle die Antwort mit allen Kontextvariablen
        answer = answer_template.format(
            topic=topic, 
            parent_topic=parent_topic,
            alternative_topic=alternative_topic,
            context=context,
            related_field=related_field
        )
        
        # Prüfe auf Duplikate
        if question.lower() not in existing_questions:
            flashcards.append({
                "question": question,
                "answer": answer
            })
            existing_questions.add(question.lower())
    
    # Fülle mit weiteren zufälligen Flashcards auf, falls noch nicht genug
    while len(flashcards) < min_count and attempts < max_attempts:
        attempts += 1
        
        # Wähle zufällig ein Thema und Kontextvariablen
        topic = random.choice(topics_to_use)
        parent_topic = main_topic if topic != main_topic else random.choice(subtopics if subtopics else ["general knowledge" if language == 'en' else "allgemeines Wissen"])
        alternative_topic = random.choice([t for t in topics_to_use if t != topic] or ["other concepts" if language == 'en' else "andere Konzepte"])
        context = random.choice(contexts)
        related_field = random.choice(related_fields)
        
        # Wähle zufällig eine Vorlage
        question_template = random.choice(question_templates)
        answer_template = random.choice(answer_templates)
        
        # Erstelle die Frage mit allen Kontextvariablen
        question = question_template.format(
            topic=topic, 
            parent_topic=parent_topic,
            alternative_topic=alternative_topic,
            context=context,
            related_field=related_field
        )
        
        # Erstelle die Antwort mit allen Kontextvariablen
        answer = answer_template.format(
            topic=topic, 
            parent_topic=parent_topic,
            alternative_topic=alternative_topic,
            context=context,
            related_field=related_field
        )
        
        # Prüfe auf Duplikate
        if question.lower() not in existing_questions:
            flashcards.append({
                "question": question,
                "answer": answer
            })
            existing_questions.add(question.lower())
    
    return flashcards