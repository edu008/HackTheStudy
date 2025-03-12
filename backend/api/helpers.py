import os
import re
import PyPDF2
from openai import OpenAI

# Configuration
ALLOWED_EXTENSIONS = {'pdf', 'txt'}
MAX_FILES = 5
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Helper functions
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

def extract_text_from_file(file):
    """Extract text from a file based on its extension"""
    file_extension = file.filename.rsplit('.', 1)[1].lower()
    file.seek(0)  # Reset file pointer to beginning
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
                {"role": "system", "content": "You are a helpful assistant for creating study materials from exam content. Ensure all generated questions and answers are directly related to the provided exam content or logically extend its topics."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise Exception(f"ChatGPT API request failed: {str(e)}")

def analyze_content(text, client):
    """Analyze the content and validate existing questions for meaningfulness."""
    prompt = f"""
    Analyze the following exam content and determine the key topics and the potential number of flashcards and multiple-choice questions that can be generated. Extract all existing questions and answers directly from the content if present. For each extracted question and answer pair, validate whether it makes sense (i.e., the question is clear and the answer is relevant and correct). Drop any pairs that are nonsensical or incomplete.

    Format your response as follows:
    Topics: [list of key topics]
    Estimated Flashcards: [number]
    Estimated Questions: [number]
    Existing Questions: [question1:answer1, question2:answer2, ...] (if none or all dropped, write 'None')

    Exam content:
    {text[:4000]}
    """
    response = query_chatgpt(prompt, client)
    print(f"\nDEBUG: Content analysis response:\n{response}\n")
    return parse_analysis(response)

def parse_analysis(response):
    """Parse the analysis response to extract topics and validated existing questions."""
    topics = []
    estimated_flashcards = 0
    estimated_questions = 0
    existing_questions = []

    lines = response.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith("Topics:"):
            topics = line[len("Topics:"):].strip().split(", ")
        elif line.startswith("Estimated Flashcards:"):
            try:
                estimated_flashcards = int(line[len("Estimated Flashcards:"):].strip())
            except ValueError:
                estimated_flashcards = 0
        elif line.startswith("Estimated Questions:"):
            try:
                estimated_questions = int(line[len("Estimated Questions:"):].strip())
            except ValueError:
                estimated_questions = 0
        elif line.startswith("Existing Questions:"):
            eq_text = line[len("Existing Questions:"):].strip()
            if eq_text != "None":
                pairs = eq_text.split(", ")
                for pair in pairs:
                    if ":" in pair:
                        q, a = pair.split(":", 1)
                        existing_questions.append({"question": q.strip(), "answer": a.strip()})

    # Fallback: Mindestanzahl sicherstellen
    estimated_flashcards = max(8, estimated_flashcards)
    estimated_questions = max(5, estimated_questions)

    return {
        "topics": topics,
        "estimated_flashcards": estimated_flashcards,
        "estimated_questions": estimated_questions,
        "existing_questions": existing_questions
    }

def generate_flashcards(text, client, existing_flashcards=None):
    """Generate exactly 5 additional flashcards based on content analysis."""
    analysis = analyze_content(text, client)
    existing_questions = analysis["existing_questions"]
    
    # Berechne, wie viele neue Fragen generiert werden sollen
    num_existing_to_use = min(5, len(existing_questions)) if existing_questions else 0
    num_new_to_generate = 5 - num_existing_to_use
    
    prompt = f"""
    Analyze the following exam content and create exactly 5 flashcards. Use existing questions and answers from the content if provided, and generate new questions to fill the remaining slots. Ensure all questions and answers make sense and are directly related to the exam content.

    Format each flashcard EXACTLY as follows:
    Question: [question]
    Answer: [answer]

    Exam content:
    {text[:4000]}

    Existing questions to include (use up to {num_existing_to_use} of these):
    {', '.join([f"{q['question']}:{q['answer']}" for q in existing_questions[:num_existing_to_use]]) if existing_questions else 'None'}

    Rules:
    - Generate exactly 5 flashcards in total.
    - Include {num_existing_to_use} existing questions from the list above (if available).
    - Generate {num_new_to_generate} new questions that are thematically relevant to the content.
    - Keep answers short and simple - maximum 2-3 sentences per answer.
    - Use simple language that is easy to understand.
    - Focus on key concepts and definitions from the content.
    - Ensure each flashcard is complete with both a clear question and a relevant answer.
    - Do not use any special formatting or numbering.
    - Avoid duplicating any questions from the following existing flashcards (if provided):
    {', '.join([f"{f['question']}:{f['answer']}" for f in existing_flashcards]) if existing_flashcards else 'None'}
    """
    
    try:
        response = query_chatgpt(prompt, client)
        print(f"\nDEBUG: Raw ChatGPT response for flashcards:\n{response}\n")
        flashcards = []
        pattern = r'Question:\s*(.+?)\s*Answer:\s*(.+?)(?=(?:\nQuestion:|\Z))'
        matches = re.finditer(pattern, response, re.DOTALL)
        
        for i, match in enumerate(matches, 1):
            question = match.group(1).strip()
            answer = match.group(2).strip()
            flashcards.append({
                "id": i,
                "question": question,
                "answer": answer
            })
        
        # Fallback, falls weniger als 5 generiert wurden
        while len(flashcards) < 5:
            flashcards.append({
                "id": len(flashcards) + 1,
                "question": f"Could not generate flashcard {len(flashcards) + 1}.",
                "answer": "Insufficient content to generate more unique flashcards."
            })
        
        print(f"DEBUG: Generated {len(flashcards)} flashcards (including {num_existing_to_use} existing)")
        return flashcards
    except Exception as e:
        print(f"Error generating flashcards: {e}")
        return [{
            "id": 1,
            "question": "Error generating flashcards",
            "answer": "There was an error processing your request. Please try again."
        }] * 5

def generate_test_questions(text, client, existing_questions_list=None):
    """Generate exactly 5 additional test questions based on content analysis."""
    analysis = analyze_content(text, client)
    existing_questions = analysis["existing_questions"]
    
    # Berechne, wie viele neue Fragen generiert werden sollen
    num_existing_to_use = min(5, len(existing_questions)) if existing_questions else 0
    num_new_to_generate = 5 - num_existing_to_use
    
    prompt = f"""
    Analyze the following exam content and create exactly 5 multiple-choice test questions. Use existing questions from the content if provided (converting them to multiple-choice format), and generate new questions to fill the remaining slots. Ensure all questions and answers make sense and are directly related to the exam content.

    Format EXACTLY as follows for each question:
    Question: [question text]
    Options:
    A. [option 1]
    B. [option 2]
    C. [option 3]
    D. [option 4]
    Correct: [A/B/C/D]
    
    Exam content:
    {text[:4000]}

    Existing questions to include (use up to {num_existing_to_use} of these, convert to multiple-choice):
    {', '.join([f"{q['question']}:{q['answer']}" for q in existing_questions[:num_existing_to_use]]) if existing_questions else 'None'}

    Rules:
    - Generate exactly 5 multiple-choice questions in total.
    - Include {num_existing_to_use} existing questions from the list above (if available), converting them to multiple-choice with plausible distractors.
    - Generate {num_new_to_generate} new questions that are thematically relevant to the content.
    - Keep questions clear and straightforward.
    - Make sure each question has exactly 4 options (A, B, C, D).
    - Ensure one and only one correct answer for each question.
    - Include questions that test understanding of key concepts from the content.
    - Do not use any special formatting or numbering.
    - Avoid duplicating any questions from the following existing test questions (if provided):
    {', '.join([f"{q['text']}:{q['options'][q['correctAnswer']]}" for q in existing_questions_list]) if existing_questions_list else 'None'}
    """
    
    try:
        response = query_chatgpt(prompt, client)
        print(f"\nDEBUG: Raw ChatGPT response for test questions:\n{response}\n")
        questions = []
        current_question = ""
        current_options = []
        current_correct = -1
        
        lines = response.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("Question:"):
                if current_question and current_options and current_correct >= 0:
                    questions.append({
                        "id": len(questions) + 1,
                        "text": current_question,
                        "options": current_options,
                        "correctAnswer": current_correct
                    })
                current_question = line[len("Question:"):].strip()
                current_options = []
                current_correct = -1
            elif line.startswith("Options:"):
                i += 1
                for _ in range(4):
                    if i < len(lines):
                        option_line = lines[i].strip()
                        if option_line.startswith(("A.", "B.", "C.", "D.")):
                            current_options.append(option_line[2:].strip())
                        i += 1
                i -= 1
            elif line.startswith("Correct:"):
                correct_letter = line[len("Correct:"):].strip()
                if correct_letter == "A":
                    current_correct = 0
                elif correct_letter == "B":
                    current_correct = 1
                elif correct_letter == "C":
                    current_correct = 2
                elif correct_letter == "D":
                    current_correct = 3
            i += 1
        
        if current_question and current_options and current_correct >= 0:
            questions.append({
                "id": len(questions) + 1,
                "text": current_question,
                "options": current_options,
                "correctAnswer": current_correct
            })
        
        # Fallback, falls weniger als 5 generiert wurden
        while len(questions) < 5:
            questions.append({
                "id": len(questions) + 1,
                "text": f"Could not generate test question {len(questions) + 1}.",
                "options": ["Try again", "Upload a different file", "Check the content", "Insufficient content"],
                "correctAnswer": 3
            })
        
        print(f"DEBUG: Generated {len(questions)} test questions (including {num_existing_to_use} existing)")
        return questions
    except Exception as e:
        print(f"Error generating test questions: {e}")
        return [{
            "id": i + 1,
            "text": "Error generating test question",
            "options": ["There was an error", "Try again", "Check the file", "Contact support"],
            "correctAnswer": 1
        } for i in range(5)]

# Beispiel zur Nutzung
if __name__ == "__main__":
    client = OpenAI(api_key="your-api-key-here")
    with open("sample.pdf", "rb") as file:
        text = extract_text_from_file(file)
        
        # Erste Generierung
        flashcards = generate_flashcards(text, client)
        test_questions = generate_test_questions(text, client)
        print("Initial Flashcards:", flashcards)
        print("Initial Test Questions:", test_questions)
        
        # Zweite Generierung (5 weitere)
        more_flashcards = generate_flashcards(text, client, flashcards)
        more_test_questions = generate_test_questions(text, client, test_questions)
        print("More Flashcards:", more_flashcards)
        print("More Test Questions:", more_test_questions)