from flask import Blueprint, request, jsonify, session, current_app
import os
import traceback
from .helpers import (
    allowed_file, 
    extract_text_from_file, 
    generate_flashcards, 
    generate_test_questions,
    MAX_FILES,
    MAX_FILE_SIZE
)

# Create a Blueprint for the API routes
api_bp = Blueprint('api', __name__)

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify API is running"""
    return jsonify({"status": "healthy", "message": "API is running"}), 200

@api_bp.route('/upload', methods=['POST'])
def upload_files():
    """Upload and process files to generate flashcards and test questions"""
    print("\n----- DEBUG: File Upload Request Received -----")
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request form data: {request.form}")
    print(f"Request files: {request.files}")
    
    # Get the OpenAI client from the app context
    client = current_app.config['OPENAI_CLIENT']
    
    if 'files[]' not in request.files:
        print("DEBUG: No files found in request")
        return jsonify({"error": "No files provided"}), 400
    
    files = request.files.getlist('files[]')
    print(f"DEBUG: Number of files received: {len(files)}")
    print(f"DEBUG: File names: {[file.filename for file in files]}")
    
    if len(files) > MAX_FILES:
        print(f"DEBUG: Too many files: {len(files)} > {MAX_FILES}")
        return jsonify({"error": f"Maximum {MAX_FILES} files allowed"}), 400
    
    for file in files:
        if file.filename == '':
            print("DEBUG: Empty filename detected")
            return jsonify({"error": "One or more files have no filename"}), 400
        
        if not allowed_file(file.filename):
            print(f"DEBUG: Invalid file type: {file.filename}")
            return jsonify({"error": f"File type not allowed. Allowed types: pdf, txt"}), 400
        
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        print(f"DEBUG: File size for {file.filename}: {file_size / (1024 * 1024):.2f} MB")
        
        if file_size > MAX_FILE_SIZE:
            print(f"DEBUG: File too large: {file_size} > {MAX_FILE_SIZE}")
            return jsonify({"error": f"File size exceeds maximum limit of {MAX_FILE_SIZE / (1024 * 1024)}MB"}), 400
    
    combined_text = ""
    
    try:
        print("\n----- DEBUG: Processing Files -----")
        for file in files:
            print(f"DEBUG: Extracting text from {file.filename}")
            text = extract_text_from_file(file)
            print(f"DEBUG: Extracted {len(text)} characters from {file.filename}")
            print(f"DEBUG: First 100 chars: {text[:100]}...")
            combined_text += text + "\n\n"
        
        print(f"\nDEBUG: Total combined text length: {len(combined_text)} characters")
        print(f"DEBUG: First 200 chars of combined text: {combined_text[:200]}...")
        
        # Speichere den Text in der Sitzung und in der App-Konfiguration als Fallback
        try:
            session['last_uploaded_text'] = combined_text
            print("DEBUG: Text in Session gespeichert")
        except Exception as e:
            print(f"DEBUG: Fehler beim Speichern in Session: {str(e)}")
        
        # Speichere auch in der App-Konfiguration als Fallback
        current_app.config['LAST_UPLOADED_TEXT'] = combined_text
        print("DEBUG: Text in App-Konfiguration gespeichert")
        
        print("\nDEBUG: Generating flashcards...")
        flashcards = generate_flashcards(combined_text, client)
        print(f"DEBUG: Generated {len(flashcards)} flashcards")
        for i, card in enumerate(flashcards[:2]):  # Print first 2 cards for debugging
            print(f"DEBUG: Flashcard {i+1}:")
            print(f"  Question: {card['question'][:50]}...")
            print(f"  Answer: {card['answer'][:50]}...")
        
        print("\nDEBUG: Generating test questions...")
        questions = generate_test_questions(combined_text, client)
        print(f"DEBUG: Generated {len(questions)} test questions")
        for i, q in enumerate(questions[:2]):  # Print first 2 questions for debugging
            print(f"DEBUG: Question {i+1}:")
            print(f"  Text: {q['text'][:50]}...")
            print(f"  Options: {[opt[:20] + '...' for opt in q['options']]}")
            print(f"  Correct Answer: {q['correctAnswer']}")
        
        response_data = {
            "success": True,
            "message": f"Successfully processed {len(files)} files",
            "flashcards": flashcards,
            "questions": questions
        }
        print("\nDEBUG: Sending response to client")
        print(f"DEBUG: Response status: 200 OK")
        print(f"DEBUG: Response contains {len(flashcards)} flashcards and {len(questions)} questions")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"\nDEBUG: ERROR during processing: {str(e)}")
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Error processing files: {str(e)}"}), 500

@api_bp.route('/generate-more-flashcards', methods=['POST'])
def generate_more_flashcards():
    """Generate additional flashcards from previously uploaded content"""
    print("\n----- DEBUG: Generate More Flashcards Request -----")
    try:
        # Get the OpenAI client from the app context
        client = current_app.config['OPENAI_CLIENT']
        
        # Versuche, den Text aus der Session zu holen, oder verwende den Fallback
        combined_text = None
        
        try:
            if 'last_uploaded_text' in session:
                combined_text = session['last_uploaded_text']
                print("DEBUG: Text aus Session geladen")
        except Exception as e:
            print(f"DEBUG: Fehler beim Laden aus Session: {str(e)}")
        
        # Fallback zur App-Konfiguration
        if not combined_text:
            combined_text = current_app.config.get('LAST_UPLOADED_TEXT', '')
            print("DEBUG: Text aus App-Konfiguration geladen")
        
        if not combined_text:
            print("DEBUG: No previous content available to generate more flashcards")
            return jsonify({"error": "No previous content available to generate more flashcards. Please upload a file first."}), 400
        print(f"DEBUG: Using previously uploaded text (length: {len(combined_text)} chars)")
        print(f"DEBUG: First 200 chars of previously uploaded text: {combined_text[:200]}...")
        
        print("DEBUG: Generating additional flashcards...")
        flashcards = generate_flashcards(combined_text, client)
        print(f"DEBUG: Generated {len(flashcards)} additional flashcards")
        
        response_data = {
            "success": True,
            "message": "Successfully generated more flashcards",
            "flashcards": flashcards,
            "questions": []
        }
        print("DEBUG: Sending response with additional flashcards")
        return jsonify(response_data), 200
    except Exception as e:
        print(f"DEBUG: ERROR generating more flashcards: {str(e)}")
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Error generating flashcards: {str(e)}"}), 500

@api_bp.route('/generate-more-questions', methods=['POST'])
def generate_more_questions():
    """Generate additional test questions from previously uploaded content"""
    print("\n----- DEBUG: Generate More Questions Request -----")
    try:
        # Get the OpenAI client from the app context
        client = current_app.config['OPENAI_CLIENT']
        
        # Versuche, den Text aus der Session zu holen, oder verwende den Fallback
        combined_text = None
        
        try:
            if 'last_uploaded_text' in session:
                combined_text = session['last_uploaded_text']
                print("DEBUG: Text aus Session geladen")
        except Exception as e:
            print(f"DEBUG: Fehler beim Laden aus Session: {str(e)}")
        
        # Fallback zur App-Konfiguration
        if not combined_text:
            combined_text = current_app.config.get('LAST_UPLOADED_TEXT', '')
            print("DEBUG: Text aus App-Konfiguration geladen")
        
        if not combined_text:
            print("DEBUG: No previous content available to generate more questions")
            return jsonify({"error": "No previous content available to generate more questions. Please upload a file first."}), 400
        print(f"DEBUG: Using previously uploaded text (length: {len(combined_text)} chars)")
        print(f"DEBUG: First 200 chars of previously uploaded text: {combined_text[:200]}...")
        
        print("DEBUG: Generating additional test questions...")
        questions = generate_test_questions(combined_text, client)
        print(f"DEBUG: Generated {len(questions)} additional test questions")
        
        response_data = {
            "success": True,
            "message": "Successfully generated more questions",
            "flashcards": [],
            "questions": questions
        }
        print("DEBUG: Sending response with additional test questions")
        return jsonify(response_data), 200
    except Exception as e:
        print(f"DEBUG: ERROR generating more questions: {str(e)}")
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Error generating questions: {str(e)}"}), 500
