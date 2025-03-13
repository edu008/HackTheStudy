import os
import re
import PyPDF2
import time  # Hinzugefügt
from openai import OpenAI
from colorama import init, Fore, Style

# Initialisiere colorama
init()

# Configuration
ALLOWED_EXTENSIONS = {'pdf', 'txt'}
MAX_FILES = 5
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Hilfsfunktionen für Debugging
def print_debug(message, success=True):
    """Hilfsfunktion für farbigen Debug-Output."""
    if success:
        print(f"{Fore.GREEN}DEBUG: {message}{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}DEBUG: {message}{Style.RESET_ALL}")

def print_loading(step):
    """Simuliert eine Ladeanzeige."""
    print(f"{Fore.CYAN}LOADING: {step}...{Style.RESET_ALL}", end="\r")
    time.sleep(0.5)

def allowed_file(filename):
    """Check if the file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_stream):
    """Extract text from a PDF file"""
    pdf_reader = PyPDF2.PdfReader(file_stream)
    text = ""
    for page in pdf_reader.pages:
        extracted_text = page.extract_text()
        if extracted_text:
            text += extracted_text + "\n"
    return text.strip()

def extract_text_from_file(file, filename=None):
    """Extract text from a file based on its extension"""
    # If filename is provided directly, use it
    # Otherwise try to get it from the file object (for Flask FileStorage objects)
    if filename is None:
        if hasattr(file, 'filename'):
            filename = file.filename
        else:
            # For file objects without filename attribute, we can't determine the extension
            raise ValueError("Filename must be provided for file objects without a filename attribute")
    
    file_extension = filename.rsplit('.', 1)[1].lower()
    file.seek(0)
    if file_extension == 'pdf':
        return extract_text_from_pdf(file)
    elif file_extension == 'txt':
        return file.read().decode('utf-8')
    return ""

def query_chatgpt(prompt, client):
    """Query the OpenAI API with a prompt"""
    if not client.api_key:
        raise ValueError("OpenAI API key is missing. Please set the OPENAI_API_KEY in the .env file.")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant for creating study materials from exam content. Analyze the content and decide how many flashcards and multiple-choice questions to generate based on its complexity and depth. Ensure all generated items are directly related to the provided content."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise Exception(f"ChatGPT API request failed: {str(e)}")

def analyze_content(text, client):
    """Analyze the content and let ChatGPT decide the number of items."""
    prompt = f"""
    Analyze the following content and determine:
    - Key topics.
    - How many flashcards should be generated based on the content's depth and complexity.
    - How many multiple-choice questions should be generated based on the content's depth and complexity.
    - Whether it is an exam or study material (based on structure and content).
    - Extract existing questions if present.

    Format:
    Topics: [list of key topics]
    Estimated Flashcards: [number]
    Estimated Questions: [number]
    Content Type: [exam/study_material]
    Existing Questions: [question1:answer1, ...] or None

    Content:
    {text[:10000]}
    """
    response = query_chatgpt(prompt, client)
    print_debug(f"Content analysis response:\n{response}")
    return parse_analysis(response)

def parse_analysis(response):
    """Parse the analysis response."""
    topics = []
    estimated_flashcards = 0
    estimated_questions = 0
    content_type = "study_material"
    existing_questions = []

    lines = response.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith("Topics:"):
            topics = line[len("Topics:"):].strip().split(", ")
        elif line.startswith("Estimated Flashcards:"):
            # Extract just the number from the string, ignoring any text in parentheses
            flashcards_text = line[len("Estimated Flashcards:"):].strip()
            # Extract the first number from the string
            import re
            flashcards_match = re.search(r'\d+', flashcards_text)
            estimated_flashcards = int(flashcards_match.group(0)) if flashcards_match else 5  # Default to 5 if no number found
        elif line.startswith("Estimated Questions:"):
            # Extract just the number from the string, ignoring any text in parentheses
            questions_text = line[len("Estimated Questions:"):].strip()
            # Extract the first number from the string
            import re
            questions_match = re.search(r'\d+', questions_text)
            estimated_questions = int(questions_match.group(0)) if questions_match else 3  # Default to 3 if no number found
        elif line.startswith("Content Type:"):
            content_type = line[len("Content Type:"):].strip()
        elif line.startswith("Existing Questions:") and "None" not in line:
            eq_text = line[len("Existing Questions:"):].strip()
            pairs = eq_text.split(", ")
            for pair in pairs:
                if ":" in pair:
                    q, a = pair.split(":", 1)
                    existing_questions.append({"question": q.strip(), "answer": a.strip()})

    estimated_flashcards = max(1, estimated_flashcards)
    estimated_questions = max(1, estimated_questions)

    return {
        "topics": topics,
        "estimated_flashcards": estimated_flashcards,
        "estimated_questions": estimated_questions,
        "content_type": content_type,
        "existing_questions": existing_questions
    }

def generate_flashcards(text, client, existing_flashcards=None):
    """Generate flashcards based on ChatGPT's estimation."""
    analysis = analyze_content(text, client)
    target_flashcards = analysis["estimated_flashcards"]
    existing_questions = analysis["existing_questions"]
    
    prompt = f"""
    Create {target_flashcards} flashcards from the following content. Use existing questions if provided, and generate new ones to reach the total number decided by you based on the content's depth.

    Format (DO NOT use markdown formatting like ** or numbering):
    Question: [question]
    Answer: [answer]

    Content:
    {text[:10000]}

    Existing questions (use as many as possible up to {target_flashcards}):
    {', '.join([f"{q['question']}:{q['answer']}" for q in existing_questions]) if existing_questions else 'None'}

    Rules:
    - Generate exactly {target_flashcards} flashcards as estimated from the content analysis.
    - Use existing questions where possible and supplement with new ones.
    - Avoid duplicates with: {', '.join([f"{f['question']}:{f['answer']}" for f in existing_flashcards]) if existing_flashcards else 'None'}
    - Ensure all flashcards are relevant to the content.
    - DO NOT use markdown formatting like ** or numbering in your response.
    - Follow the exact format specified above.
    """
    
    try:
        response = query_chatgpt(prompt, client)
        print_debug(f"Raw ChatGPT response for flashcards:\n{response}")
        flashcards = []
        pattern = r'(?:Question:|^\d+\.\s+\*\*Question:\*\*)\s*(.+?)\s*(?:Answer:|^\s*\*\*Answer:\*\*)\s*(.+?)(?=(?:\n(?:Question:|\d+\.\s+\*\*Question:\*\*)|\Z))'
        matches = re.finditer(pattern, response, re.DOTALL)
        
        for i, match in enumerate(matches, 1):
            question = match.group(1).strip()
            answer = match.group(2).strip()
            flashcards.append({"id": i, "question": question, "answer": answer})
        
        while len(flashcards) < target_flashcards:
            flashcards.append({
                "id": len(flashcards) + 1,
                "question": f"Could not generate flashcard {len(flashcards) + 1}.",
                "answer": "Insufficient content."
            })
        
        return flashcards
    except Exception as e:
        print_debug(f"Error generating flashcards: {e}", success=False)
        return [{"id": i, "question": "Error", "answer": "Try again."} for i in range(1, target_flashcards + 1)]

def generate_test_questions(text, client, existing_questions_list=None):
    """Generate test questions based on ChatGPT's estimation."""
    analysis = analyze_content(text, client)
    target_questions = analysis["estimated_questions"]
    existing_questions = analysis["existing_questions"]
    
    prompt = f"""
    Create {target_questions} multiple-choice questions from the following content. Use existing questions if provided, and generate new ones to reach the total number decided by you based on the content's depth.

    Format (DO NOT use markdown formatting like ** or numbering):
    Question: [question]
    Options:
    A. [option 1]
    B. [option 2]
    C. [option 3]
    D. [option 4]
    Correct: [A/B/C/D]
    Explanation: [brief explanation of why the correct answer is correct]

    Content:
    {text[:10000]}

    Existing questions (use as many as possible up to {target_questions}):
    {', '.join([f"{q['question']}:{q['answer']}" for q in existing_questions]) if existing_questions else 'None'}

    Rules:
    - Generate exactly {target_questions} questions as estimated from the content analysis.
    - Use existing questions where possible and supplement with new ones.
    - Avoid duplicates with: {', '.join([f"{q['text']}:{q['options'][q['correctAnswer']]}" for q in existing_questions_list]) if existing_questions_list else 'None'}
    - Ensure all questions are relevant to the content.
    - Include a brief explanation for each correct answer.
    - DO NOT use markdown formatting like ** or numbering in your response.
    - Follow the exact format specified above.
    """
    
    try:
        response = query_chatgpt(prompt, client)
        print_debug(f"Raw ChatGPT response for test questions:\n{response}")
        questions = []
        pattern = r'(?:Question:|^\d+\.\s+\*\*Question:\*\*)\s*(.+?)\s*(?:Options:|^\s*\*\*Options:\*\*)\s*(?:A\.|^\s*A\.)\s*(.+?)\s*(?:B\.|^\s*B\.)\s*(.+?)\s*(?:C\.|^\s*C\.)\s*(.+?)\s*(?:D\.|^\s*D\.)\s*(.+?)\s*(?:Correct:|^\s*\*\*Correct:\*\*)\s*([A-D])\s*(?:Explanation:|^\s*\*\*Explanation:\*\*)\s*(.+?)(?=(?:\n(?:Question:|\d+\.\s+\*\*Question:\*\*)|\Z))'
        matches = re.finditer(pattern, response, re.DOTALL)
        
        correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        for i, match in enumerate(matches, 1):
            questions.append({
                "id": i,
                "text": match.group(1).strip(),
                "options": [match.group(2).strip(), match.group(3).strip(), match.group(4).strip(), match.group(5).strip()],
                "correctAnswer": correct_map[match.group(6)],
                "explanation": match.group(7).strip()
            })
        
        while len(questions) < target_questions:
            questions.append({
                "id": len(questions) + 1,
                "text": f"Could not generate question {len(questions) + 1}.",
                "options": ["Try again", "Upload more content", "Check file", "Insufficient data"],
                "correctAnswer": 3
            })
        
        return questions
    except Exception as e:
        print_debug(f"Error generating test questions: {e}", success=False)
        return [{"id": i, "text": "Error", "options": ["Try again", "Check file", "Contact support", "N/A"], "correctAnswer": 0} for i in range(1, target_questions + 1)]
