import os
import uuid
import json
import time
from flask import Blueprint, request, jsonify, current_app, session
from .utils import allowed_file, extract_text_from_file, generate_flashcards, generate_test_questions, analyze_content, print_debug, print_loading

api_bp = Blueprint('api', __name__)

@api_bp.route('/upload', methods=['POST'])
def upload_file():
    print_loading("Checking file upload")
    if 'file' not in request.files:
        print_debug("No file part in request", success=False)
        return jsonify({'error': 'No file part'}), 400
    
    files = request.files.getlist('file')
    if not files or len(files) > 5:
        print_debug(f"Invalid number of files: {len(files)}. Max 5 allowed.", success=False)
        return jsonify({'error': 'Max 5 files allowed'}), 400
    
    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    session_path = os.path.join(current_app.config['TEMP_FOLDER'], session_id)
    os.makedirs(session_path, exist_ok=True)
    print_debug(f"Created session {session_id} at {session_path}")
    
    all_text = ""
    print_loading("Extracting text from files")
    for file in files:
        if not allowed_file(file.filename):
            print_debug(f"Invalid file type: {file.filename}", success=False)
            return jsonify({'error': f'Invalid file type: {file.filename}'}), 400
        
        file_path = os.path.join(session_path, file.filename)
        file.save(file_path)
        
        with open(file_path, 'rb') as f:
            text = extract_text_from_file(f, filename=file.filename)
            all_text += text + "\n"
    
    text_file_path = os.path.join(session_path, 'combined_text.txt')
    with open(text_file_path, 'w', encoding='utf-8') as f:
        f.write(all_text)
    print_debug(f"Extracted and saved text to {text_file_path}")
    
    print_loading("Analyzing content with OpenAI")
    client = current_app.config['OPENAI_CLIENT']
    try:
        analysis = analyze_content(all_text, client)
        content_type = analysis.get("content_type", "unknown")
        print_debug(f"Content analyzed. Type: {content_type}")
        print_debug(f"Key topics: {', '.join(analysis['topics'])}")
        print_debug(f"Estimated flashcards: {analysis['estimated_flashcards']}, questions: {analysis['estimated_questions']}")
    except Exception as e:
        print_debug(f"Content analysis failed: {str(e)}", success=False)
        content_type = "unknown"
        analysis = {'topics': [], 'estimated_flashcards': 0, 'estimated_questions': 0, 'existing_questions': [], 'content_type': 'unknown'}
    
    print_loading("Generating flashcards")
    try:
        flashcards = generate_flashcards(all_text, client)
        print_debug(f"Generated {len(flashcards)} flashcards (estimated: {analysis['estimated_flashcards']})")
    except Exception as e:
        print_debug(f"Flashcard generation failed: {str(e)}", success=False)
        flashcards = []
    
    print_loading("Generating test questions")
    try:
        test_questions = generate_test_questions(all_text, client)
        print_debug(f"Generated {len(test_questions)} test questions (estimated: {analysis['estimated_questions']})")
    except Exception as e:
        print_debug(f"Test question generation failed: {str(e)}", success=False)
        test_questions = []
    
    result_path = os.path.join(session_path, 'results.json')
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump({
            'flashcards': flashcards,
            'test_questions': test_questions,
            'analysis': {
                'content_type': content_type,
                'topics': analysis['topics'],
                'estimated_flashcards': analysis['estimated_flashcards'],
                'estimated_questions': analysis['estimated_questions']
            }
        }, f)
    print_debug(f"Saved results to {result_path}")
    
    print_loading("Sending response to client")
    response = {
        'session_id': session_id,
        'flashcards': flashcards,
        'questions': test_questions,  # Changed from 'test_questions' to 'questions' to match frontend expectations
        'success': True,  # Added to match frontend expectations
        'message': 'Files processed successfully',  # Added to match frontend expectations
        'analysis': {
            'content_type': content_type,
            'topics': analysis['topics'],
            'estimated_flashcards': analysis['estimated_flashcards'],
            'estimated_questions': analysis['estimated_questions']
        }
    }
    print_debug(f"Response sent with {len(flashcards)} flashcards and {len(test_questions)} test questions")
    return jsonify(response), 200

@api_bp.route('/results/<session_id>', methods=['GET'])
def get_results(session_id):
    session_path = os.path.join(current_app.config['TEMP_FOLDER'], session_id)
    result_path = os.path.join(session_path, 'results.json')
    
    if not os.path.exists(result_path):
        print_debug(f"Session {session_id} not found or expired", success=False)
        return jsonify({'error': 'Session not found or expired'}), 404
    
    with open(result_path, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    # Transform the results to match the frontend's expected structure
    response = {
        'session_id': session_id,
        'flashcards': results.get('flashcards', []),
        'questions': results.get('test_questions', []),  # Changed from 'test_questions' to 'questions'
        'success': True,
        'message': 'Results retrieved successfully',
        'analysis': results.get('analysis', {})
    }
    
    print_debug(f"Retrieved results for session {session_id}")
    return jsonify(response), 200

@api_bp.route('/generate-more-flashcards', methods=['POST'])
def generate_more_flashcards():
    if 'session_id' not in session:
        print_debug("No active session found", success=False)
        return jsonify({'error': 'No active session found. Please upload files first.'}), 400
    
    session_id = session['session_id']
    session_path = os.path.join(current_app.config['TEMP_FOLDER'], session_id)
    text_file_path = os.path.join(session_path, 'combined_text.txt')
    result_path = os.path.join(session_path, 'results.json')
    
    if not os.path.exists(text_file_path) or not os.path.exists(result_path):
        print_debug(f"Session {session_id} not found or expired", success=False)
        return jsonify({'error': 'Session not found or expired'}), 404
    
    # Load existing results
    with open(result_path, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    existing_flashcards = results.get('flashcards', [])
    
    # Load the text content
    with open(text_file_path, 'r', encoding='utf-8') as f:
        all_text = f.read()
    
    print_loading("Generating additional flashcards")
    client = current_app.config['OPENAI_CLIENT']
    try:
        # Generate 5 more flashcards
        new_flashcards = generate_flashcards(all_text, client, existing_flashcards)
        # Take only the first 5 (or less if fewer were generated)
        new_flashcards = new_flashcards[:5]
        
        # Update IDs to continue from the last existing flashcard
        start_id = len(existing_flashcards) + 1
        for i, card in enumerate(new_flashcards):
            card['id'] = start_id + i
        
        print_debug(f"Generated {len(new_flashcards)} additional flashcards")
        
        # Update the results file with the new flashcards
        results['flashcards'] = existing_flashcards + new_flashcards
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(results, f)
        
        response = {
            'success': True,
            'message': 'Additional flashcards generated successfully',
            'flashcards': new_flashcards,
            'questions': []  # No new questions in this endpoint
        }
        return jsonify(response), 200
    except Exception as e:
        print_debug(f"Error generating additional flashcards: {str(e)}", success=False)
        return jsonify({
            'error': f'Failed to generate additional flashcards: {str(e)}',
            'success': False
        }), 500

@api_bp.route('/generate-more-questions', methods=['POST'])
def generate_more_questions():
    if 'session_id' not in session:
        print_debug("No active session found", success=False)
        return jsonify({'error': 'No active session found. Please upload files first.'}), 400
    
    session_id = session['session_id']
    session_path = os.path.join(current_app.config['TEMP_FOLDER'], session_id)
    text_file_path = os.path.join(session_path, 'combined_text.txt')
    result_path = os.path.join(session_path, 'results.json')
    
    if not os.path.exists(text_file_path) or not os.path.exists(result_path):
        print_debug(f"Session {session_id} not found or expired", success=False)
        return jsonify({'error': 'Session not found or expired'}), 404
    
    # Load existing results
    with open(result_path, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    existing_questions = results.get('test_questions', [])
    
    # Load the text content
    with open(text_file_path, 'r', encoding='utf-8') as f:
        all_text = f.read()
    
    print_loading("Generating additional test questions")
    client = current_app.config['OPENAI_CLIENT']
    try:
        # Generate 3 more questions
        new_questions = generate_test_questions(all_text, client, existing_questions)
        # Take only the first 3 (or less if fewer were generated)
        new_questions = new_questions[:3]
        
        # Update IDs to continue from the last existing question
        start_id = len(existing_questions) + 1
        for i, question in enumerate(new_questions):
            question['id'] = start_id + i
        
        print_debug(f"Generated {len(new_questions)} additional test questions")
        
        # Update the results file with the new questions
        results['test_questions'] = existing_questions + new_questions
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(results, f)
        
        response = {
            'success': True,
            'message': 'Additional test questions generated successfully',
            'flashcards': [],  # No new flashcards in this endpoint
            'questions': new_questions  # Changed from 'test_questions' to 'questions' to match frontend expectations
        }
        return jsonify(response), 200
    except Exception as e:
        print_debug(f"Error generating additional test questions: {str(e)}", success=False)
        return jsonify({
            'error': f'Failed to generate additional test questions: {str(e)}',
            'success': False
        }), 500
