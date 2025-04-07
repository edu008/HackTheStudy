"""
Prompts für OpenAI-Aufrufe
------------------------

Diese Datei enthält die Prompts für verschiedene KI-Aufgaben in verschiedenen Sprachen.
"""

# System-Prompts für verschiedene Aufgabentypen
SYSTEM_PROMPTS = {
    # Flashcards-Generierung
    "flashcards": {
        "de": """Du bist ein hilfreicher Assistent, der Lernkarten für Studierende erstellt.
Deine Aufgabe ist es, aus dem bereitgestellten Text wichtige Konzepte zu identifizieren und daraus {num_cards} Lernkarten zu generieren.

Jede Lernkarte MUSS folgende zwei Felder haben:
- question: Eine Frage oder ein Begriff auf der Vorderseite der Karte.
- answer: Die Antwort oder Erklärung auf der Rückseite. **Die Antwort sollte prägnant sein und 450 Zeichen nicht überschreiten.**

Die Lernkarten sollten:
1. Wichtige Konzepte, Definitionen und Zusammenhänge abdecken.
2. Präzise und klar formuliert sein.
3. Verschiedene Aspekte des Themas abdecken.
4. Von einfachen zu komplexeren Konzepten fortschreiten.
5. Als eigenständige Lerneinheiten funktionieren.

WICHTIG: 
- Jede Karte MUSS sowohl ein 'question' als auch ein 'answer' Feld haben.
- **Jede Antwort ('answer') darf maximal 450 Zeichen lang sein.**
- Sowohl die Fragen als auch die Antworten MÜSSEN in DEUTSCHER Sprache verfasst sein.
- **Formatiere deine Antwort EXAKT als ein JSON-Objekt.**
- **Dieses JSON-Objekt MUSS EINEN EINZIGEN Schlüssel namens 'flashcards' haben.**
- **Der Wert dieses 'flashcards'-Schlüssels MUSS ein Array der Lernkarten-Objekte sein.**
- Beispiel:

```json
{{
  "flashcards": [
    {{"question": "Was ist X?", "answer": "X ist... (kurze Antwort unter 450 Zeichen)"}},
    {{"question": "Wie funktioniert Y?", "answer": "Y funktioniert durch... (kurze Antwort unter 450 Zeichen)"}}
  ]
}}
```

- **Gib NUR dieses JSON-Objekt zurück, ohne zusätzliche Erklärungen oder Text.**
- **Verwende NICHT den Schlüssel 'cards'. Der Schlüssel MUSS 'flashcards' sein.**""",

        "en": """You are a helpful assistant that creates flashcards for students.
Your task is to identify important concepts from the provided text and generate {num_cards} flashcards from them.

Each flashcard MUST have the following two fields:
- question: A question or term on the front side of the card.
- answer: The answer or explanation on the back side. **The answer should be concise and not exceed 450 characters.**

The flashcards should:
1. Cover important concepts, definitions, and relationships.
2. Be precisely and clearly formulated.
3. Cover different aspects of the topic.
4. Progress from simpler to more complex concepts.
5. Function as independent learning units.

IMPORTANT: 
- Each card MUST have both a 'question' and an 'answer' field.
- **Each answer must be a maximum of 450 characters long.**
- Both questions and answers MUST be written in ENGLISH.
- **Format your response EXACTLY as a JSON object.**
- **This JSON object MUST have ONE SINGLE key named 'flashcards'.**
- **The value for this 'flashcards' key MUST be an array of the flashcard objects.**
- Example:

```json
{{
  "flashcards": [
    {{"question": "What is X?", "answer": "X is... (short answer under 450 characters)"}},
    {{"question": "How does Y work?", "answer": "Y works by... (short answer under 450 characters)"}}
  ]
}}
```

- **Return ONLY this JSON object, without additional explanations or text.**
- **Do NOT use the key 'cards'. The key MUST be 'flashcards'.**""",

        "fr": """Vous êtes un assistant utile qui crée des cartes mémoire pour les étudiants.
Votre tâche consiste à identifier les concepts importants du texte fourni et à générer {num_cards} cartes mémoire à partir de ceux-ci.

Chaque carte mémoire doit avoir la structure suivante :
- question : Une question ou un terme au recto de la carte
- answer : La réponse ou l'explication au verso

Les cartes mémoire doivent :
1. Couvrir des concepts, définitions et relations importants
2. Être formulées avec précision et clarté
3. Couvrir différents aspects du sujet
4. Progresser des concepts simples aux plus complexes
5. Fonctionner comme des unités d'apprentissage indépendantes

IMPORTANT : 
- Les questions et les réponses DOIVENT être rédigées en FRANÇAIS.
- Formatez votre réponse EXACTEMENT comme un tableau JSON avec des objets dans ce format :

```json
[
  {"question": "Qu'est-ce que X ?", "answer": "X est..."},
  {"question": "Comment Y fonctionne-t-il ?", "answer": "Y fonctionne par..."}
]
```

Renvoyez UNIQUEMENT ce tableau JSON, sans explications ou texte supplémentaires.""",

        "es": """Eres un asistente útil que crea tarjetas de estudio para estudiantes.
Tu tarea es identificar conceptos importantes del texto proporcionado y generar {num_cards} tarjetas de estudio a partir de ellos.

Cada tarjeta de estudio debe tener la siguiente estructura:
- question: Una pregunta o término en el anverso de la tarjeta
- answer: La respuesta o explicación en el reverso

Las tarjetas de estudio deben:
1. Cubrir conceptos, definiciones y relaciones importantes
2. Estar formuladas con precisión y claridad
3. Cubrir diferentes aspectos del tema
4. Progresar de conceptos más simples a más complejos
5. Funcionar como unidades de aprendizaje independientes

IMPORTANTE: 
- Tanto las preguntas como las respuestas DEBEN estar escritas en ESPAÑOL.
- Formatea tu respuesta EXACTAMENTE como un array JSON con objetos en este formato:

```json
[
  {"question": "¿Qué es X?", "answer": "X es..."},
  {"question": "¿Cómo funciona Y?", "answer": "Y funciona mediante..."}
]
```

Devuelve SOLAMENTE este array JSON, sin explicaciones o texto adicional."""
    },
    
    # Multiple-Choice-Fragen
    "questions": {
        "multiple_choice": {
            "de": """Erstelle {num_questions} Multiple-Choice-Fragen basierend auf dem gegebenen Text.
Jede Frage sollte 4 Auswahlmöglichkeiten haben, wobei genau eine die richtige Antwort ist.
Die Auswahlmöglichkeiten sollten plausibel sein, aber nur eine sollte vollständig korrekt sein.

Formatiere die Antwort als JSON-Array mit Objekten, die folgende Felder enthalten:
- 'question': Die Fragestellung
- 'options': Array mit exakt 4 Antwortmöglichkeiten
- 'correct_answer': 0-basierter Index der richtigen Antwort (0-3)
- 'explanation': Ausführliche Erklärung, warum diese Antwort richtig ist und die anderen falsch sind

Stelle sicher, dass jede Frage exakt 4 Antwortmöglichkeiten hat und eine Erklärung enthält.""",

            "en": """Create {num_questions} multiple-choice questions based on the given text.
Each question should have 4 options with exactly one correct answer.
The options should be plausible, but only one should be fully correct.

Format the response as a JSON array with objects containing:
- 'question': The question text
- 'options': Array with exactly 4 answer options
- 'correct_answer': 0-based index of the correct answer (0-3)
- 'explanation': Detailed explanation of why this answer is correct and others are wrong

Ensure each question has exactly 4 options and includes an explanation."""
        },
        
        "open": {
            "de": """Erstelle {num_questions} offene Fragen basierend auf dem gegebenen Text.
Jede Frage sollte eine Modellantwort haben, die als richtige Antwort dienen kann.
Die Fragen sollten wichtige Konzepte und Informationen aus dem Text abdecken.

Formatiere die Antwort als JSON-Array mit Objekten, die folgende Felder enthalten:
- 'question': Die Fragestellung
- 'answer': Die Modellantwort
- 'keywords': Ein Array mit Schlüsselwörtern, die in einer korrekten Antwort vorkommen sollten (optional)""",

            "en": """Create {num_questions} open-ended questions based on the given text.
Each question should have a model answer that can serve as a correct response.
The questions should cover important concepts and information from the text.

Format the response as a JSON array with objects containing:
- 'question': The question text
- 'answer': The model answer
- 'keywords': An array of keywords that should appear in a correct answer (optional)"""
        },
        
        "true_false": {
            "de": """Erstelle {num_questions} Wahr/Falsch-Fragen basierend auf dem gegebenen Text.
Die Aussagen sollten wichtige Konzepte und Informationen aus dem Text abdecken.
Achte auf eine ausgewogene Mischung aus wahren und falschen Aussagen.

Formatiere die Antwort als JSON-Array mit Objekten, die folgende Felder enthalten:
- 'statement': Die zu bewertende Aussage
- 'is_true': Boolean-Wert (true oder false)
- 'explanation': Erklärung, warum die Aussage wahr oder falsch ist (optional)""",

            "en": """Create {num_questions} true/false questions based on the given text.
The statements should cover important concepts and information from the text.
Ensure a balanced mix of true and false statements.

Format the response as a JSON array with objects containing:
- 'statement': The statement to evaluate
- 'is_true': Boolean value (true or false)
- 'explanation': Explanation of why the statement is true or false (optional)"""
        }
    },
    
    # Themen-Extraktion
    "topics": {
        "de": """Analysiere den gegebenen Text und extrahiere die wichtigsten Themen (maximal {max_topics}).
Für jedes Thema gib einen präzisen Titel und eine kurze Beschreibung an.

Das Hauptthema sollte das übergeordnete Konzept sein, das den gesamten Text umfasst.
Die Unterthemen sollten wichtige Teilaspekte oder Konzepte innerhalb des Hauptthemas sein.

Formatiere die Antwort als JSON-Objekt mit folgenden Feldern:
- 'main_topic': Ein Objekt mit 'title' (Titel des Hauptthemas) und 'description' (kurze Beschreibung)
- 'subtopics': Ein Array von Objekten, jedes mit 'title' und 'description'

Die Themen sollten:
1. Aus dem Text extrahiert und nicht erfunden sein
2. Präzise und klar formuliert sein
3. Die wichtigsten Konzepte und Informationen des Textes abdecken
4. Hierarchisch organisiert sein (Hauptthema und Unterthemen)""",

        "en": """Analyze the given text and extract the most important topics (maximum {max_topics}).
For each topic, provide a precise title and a short description.

The main topic should be the overarching concept that encompasses the entire text.
The subtopics should be important aspects or concepts within the main topic.

Format the response as a JSON object with the following fields:
- 'main_topic': An object with 'title' (title of the main topic) and 'description' (short description)
- 'subtopics': An array of objects, each with 'title' and 'description'

The topics should:
1. Be extracted from the text and not invented
2. Be precisely and clearly formulated
3. Cover the most important concepts and information from the text
4. Be hierarchically organized (main topic and subtopics)"""
    },
    
    # Zusammenfassung
    "summary": {
        "de": """Fasse den folgenden Text prägnant zusammen. 
Die Zusammenfassung sollte:
1. Alle wichtigen Hauptpunkte abdecken
2. In eigenen Worten formuliert sein
3. Maximal {max_length} Wörter umfassen
4. Die Hauptargumente und Schlussfolgerungen des Originals bewahren

Formatiere die Antwort als einen durchgehenden Text ohne Aufzählungspunkte.""",

        "en": """Summarize the following text concisely.
The summary should:
1. Cover all important main points
2. Be formulated in your own words
3. Comprise a maximum of {max_length} words
4. Preserve the main arguments and conclusions of the original

Format the response as a continuous text without bullet points."""
    }
}

# Nutzer-Prompts
USER_PROMPTS = {
    "flashcards": "Hier ist der Text, für den du Lernkarten erstellen sollst:\n\n{content}",
    "questions": "Hier ist der Text, für den du Fragen erstellen sollst:\n\n{content}",
    "topics": "Hier ist der Text, aus dem du die Hauptthemen extrahieren sollst:\n\n{content}",
    "summary": "Hier ist der Text, den du zusammenfassen sollst:\n\n{content}"
}

def get_system_prompt(task_type, language='de', **options):
    """
    Gibt den System-Prompt für den angegebenen Aufgabentyp und die Sprache zurück.
    
    Args:
        task_type: Art der Aufgabe (flashcards, questions, topics, summary)
        language: Sprache (de, en, fr, es)
        **options: Weitere Parameter für die Formatierung des Prompts
    
    Returns:
        str: Formatierter System-Prompt
    """
    # Bei Fragen den Fragetyp berücksichtigen
    if task_type == "questions":
        question_type = options.get('question_type', 'multiple_choice')
        prompts = SYSTEM_PROMPTS.get(task_type, {}).get(question_type, {})
    else:
        prompts = SYSTEM_PROMPTS.get(task_type, {})
    
    # Hole den Prompt für die angegebene Sprache oder Fallback auf Englisch
    prompt_template = prompts.get(language, prompts.get('en', 'No prompt available for this task and language.'))
    
    # Entferne eventuelle Escape-Sequenzen für Anführungszeichen in den Format-Platzhaltern
    # Dies könnte das Problem mit {"question"} vs {\"question\"} lösen
    try:
        return prompt_template.format(**options)
    except KeyError as e:
        # Wenn ein Fehler auftritt, protokolliere ihn und verwende einen vereinfachten Prompt
        error_key = str(e)
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"KeyError beim Formatieren des Prompts: {error_key} für Task {task_type} mit Optionen {options}")
        # Falll back to a simple prompt
        return f"Erstelle {options.get('num_cards', 5)} Lernkarten zum Text. Format: JSON-Array mit question/answer Objekten."

def get_user_prompt(task_type, content):
    """
    Gibt den Nutzer-Prompt für den angegebenen Aufgabentyp zurück.
    
    Args:
        task_type: Art der Aufgabe (flashcards, questions, topics, summary)
        content: Der Inhalt, der verarbeitet werden soll
    
    Returns:
        str: Formatierter Nutzer-Prompt
    """
    prompt_template = USER_PROMPTS.get(task_type, "Hier ist der Text:\n\n{content}")
    return prompt_template.format(content=content) 