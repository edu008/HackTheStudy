import os
import sys
from celery import Celery
import logging

# Add the current directory to the Python path to ensure app.py is found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Create the Celery instance
celery = Celery(
    'tasks',
    broker=os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://redis:6379/0')
)

logger = logging.getLogger(__name__)

# Function to create or get the Flask app
def get_flask_app():
    try:
        from app import create_app
    except ImportError:
        import os
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app import create_app
    from flask import current_app
    if current_app:
        return current_app
    return create_app()

# Configure Celery to use Flask app context
def init_celery(flask_app):
    celery.conf.update(flask_app.config)
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            app = get_flask_app()
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask

@celery.task(bind=True)
def process_upload(self, session_id, files_data, user_id=None, openai_client=None):
    app = get_flask_app()
    with app.app_context():
        logger.info(f"Starting task for session_id: {session_id}, user_id: {user_id}")
        logger.info("Running updated tasks.py version 2025-03-17")
        try:
            from api.utils import extract_text_from_file, analyze_content, generate_flashcards, generate_test_questions, detect_language
            from models import db, Upload, Flashcard, Question, Topic, UserActivity
            import httpx
            
            os.environ["HTTP_PROXY"] = ""
            os.environ["HTTPS_PROXY"] = ""
            logger.info(f"HTTP_PROXY set to: '{os.getenv('HTTP_PROXY')}'")
            logger.info(f"HTTPS_PROXY set to: '{os.getenv('HTTPS_PROXY')}'")
            
            logger.info("Extracting text from files...")
            all_text = ""
            file_names = []
            for file_name, file_content in files_data:
                text = extract_text_from_file(file_content, file_name)
                all_text += text + "\n"
                file_names.append(file_name)
            logger.info(f"Text extracted: {len(all_text)} characters, files: {file_names}")
            
            logger.info("Detecting language...")
            detected_language = detect_language(all_text)
            logger.info(f"Detected language: {detected_language}")
            
            logger.info("Initializing OpenAI client...")
            if openai_client:
                client = openai_client
            else:
                from openai import OpenAI
                client = OpenAI(
                    api_key=app.config['OPENAI_API_KEY'],
                    http_client=httpx.Client()
                )
            
            logger.info("Analyzing content...")
            analysis = analyze_content(all_text, client, language=detected_language) or {
                'main_topic': 'Unknown Topic',
                'subtopics': [],
                'estimated_flashcards': 0,
                'estimated_questions': 0,
                'existing_questions': [],
                'content_type': 'unknown'
            }
            logger.info(f"Analysis completed: {analysis}")
            
            logger.info("Generating flashcards...")
            flashcards = generate_flashcards(all_text, client, analysis=analysis, language=detected_language) or []
            logger.info(f"Generated {len(flashcards)} flashcards")
            
            logger.info("Generating test questions...")
            test_questions = generate_test_questions(all_text, client, analysis=analysis, language=detected_language) or []
            logger.info(f"Generated {len(test_questions)} test questions")
            
            logger.info("Saving upload record to database...")
            upload = Upload(session_id=session_id, user_id=user_id, file_name=", ".join(file_names), content=all_text)
            db.session.add(upload)
            db.session.commit()
            logger.info(f"Upload record created for session_id: {session_id}, upload_id: {upload.id}")
            
            logger.info("Saving main topic...")
            main_topic = Topic(upload_id=upload.id, name=analysis['main_topic'], is_main_topic=True)
            db.session.add(main_topic)
            db.session.commit()
            
            logger.info("Saving subtopics and creating connections...")
            from models import Connection
            subtopics = []
            for subtopic_name in analysis['subtopics']:
                subtopic = Topic(upload_id=upload.id, name=subtopic_name, is_main_topic=False, parent_id=main_topic.id)
                db.session.add(subtopic)
                subtopics.append(subtopic)
            
            # Flush to get IDs for the subtopics
            db.session.flush()
            
            # Create connections between main topic and each subtopic
            for subtopic in subtopics:
                connection = Connection(
                    upload_id=upload.id,
                    source_id=main_topic.id,
                    target_id=subtopic.id,
                    label=f"{main_topic.name} relates to {subtopic.name}"
                )
                db.session.add(connection)
                logger.info(f"Created connection: {main_topic.name} -> {subtopic.name}")
            
            logger.info("Saving flashcards...")
            for fc in flashcards:
                if fc.get('question') and fc.get('answer') and not fc['question'].startswith('Could not generate'):
                    db.session.add(Flashcard(upload_id=upload.id, question=fc['question'], answer=fc['answer']))
            
            logger.info("Saving test questions...")
            for q in test_questions:
                if q.get('text') and q.get('options') and not q['text'].startswith('Could not generate'):
                    # Korrigiere correct_answer: Wenn es ein String ist, finde den Index in options
                    correct_answer = q.get('correct', 0)
                    if isinstance(correct_answer, str):
                        try:
                            correct_answer = q['options'].index(correct_answer)
                        except ValueError:
                            correct_answer = 0  # Fallback, falls der Text nicht in options ist
                    db.session.add(Question(
                        upload_id=upload.id,
                        text=q['text'],
                        options=q['options'],
                        correct_answer=correct_answer,
                        explanation=q.get('explanation', '')
                    ))
            
            if user_id:
                logger.info("Recording user activity...")
                db.session.add(UserActivity(
                    user_id=user_id,
                    activity_type='upload',
                    title=f"Analyzed: {analysis['main_topic']}",
                    details={'main_topic': analysis['main_topic'], 'subtopics': analysis['subtopics'], 'session_id': session_id}
                ))
            
            logger.info("Committing all changes to database...")
            db.session.commit()
            logger.info(f"Task completed for session_id: {session_id}, flashcards: {len(flashcards)}, questions: {len(test_questions)}")
            return {"session_id": session_id, "flashcards": flashcards, "questions": test_questions, "analysis": analysis}
        except Exception as e:
            logger.error(f"Task failed for session_id: {session_id}, error: {str(e)}")
            raise
