def create_openai_client(api_key=None):
    """
    Erstellt einen OpenAI-Client mit dem v2 API Header.
    
    Args:
        api_key (str, optional): OpenAI API Key. Wenn nicht angegeben, wird der Key aus den Umgebungsvariablen gelesen.
        
    Returns:
        OpenAI: Initialisierter OpenAI-Client
    """
    import os
    from openai import OpenAI
    
    logger.debug("Erstelle OpenAI Client")
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
        logger.debug("API Key aus Umgebungsvariablen gelesen")
    
    if not api_key:
        logger.error("Kein OpenAI API Key gefunden")
        raise ValueError("OpenAI API Key nicht gefunden")
    
    logger.debug("Initialisiere OpenAI Client mit v2 API Header")
    client = OpenAI(
        api_key=api_key,
        default_headers={
            "OpenAI-Beta": "assistants=v2"
        }
    )
    logger.info("OpenAI Client erfolgreich initialisiert")
    return client

def analyze_with_assistants_api(file_path, query, model="gpt-4", instructions=None):
    """
    Analysiert eine Datei mit der OpenAI Assistants API.
    
    Args:
        file_path (str): Pfad zur zu analysierenden Datei
        query (str): Die zu analysierende Anfrage
        model (str): Das zu verwendende OpenAI-Modell
        instructions (str, optional): Zusätzliche Anweisungen für den Assistant
        
    Returns:
        str: Die Antwort des Assistenten
    """
    import os
    import time
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Erstelle den OpenAI-Client
    client = create_openai_client()
    
    # Lade die Datei hoch
    with open(file_path, "rb") as file:
        response = client.files.create(
            file=file,
            purpose="assistants"
        )
    file_id = response.id
    logger.info(f"Datei hochgeladen: {file_id}")
    
    try:
        # Erstelle einen Assistant mit der hochgeladenen Datei
        # Wichtig: Nutze beta.assistants für v2 API
        assistant = client.beta.assistants.create(
            name="Document Analyzer",
            instructions=instructions or "Analysiere die Datei und beantworte die Frage detailliert.",
            model=model,
            tools=[{"type": "file_search"}],
            file_ids=[file_id]
        )
        logger.info(f"Assistant erstellt: {assistant.id}")
        
        # Erstelle einen Thread
        thread = client.beta.threads.create()
        logger.info(f"Thread erstellt: {thread.id}")
        
        # Füge die Nachricht hinzu
        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt
        )
        logger.info(f"Nachricht hinzugefügt: {message.id}")
        
        # Starte den Run
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id
        )
        logger.info(f"Run gestartet: {run.id}")
        
        # Warte auf Abschluss des Runs (mit Timeout)
        start_time = time.time()
        timeout = 180  # Sekunden
        
        while run.status in ["queued", "in_progress"]:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Run hat Timeout von {timeout} Sekunden überschritten")
            
            time.sleep(1)
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
        
        logger.info(f"Run abgeschlossen mit Status: {run.status}")
        
        if run.status == "completed":
            # Hole die Antwort
            messages = client.beta.threads.messages.list(
                thread_id=thread.id
            )
            
            # Filtere nach Nachrichten des Assistants, die nach unserer Anfrage erstellt wurden
            assistant_messages = [
                msg for msg in messages.data 
                if msg.role == "assistant" and msg.created_at > message.created_at
            ]
            
            if assistant_messages:
                # Nehme die neueste Nachricht
                latest_message = assistant_messages[0]
                
                # Extrahiere den Text
                result = ""
                for content_item in latest_message.content:
                    if content_item.type == "text":
                        result += content_item.text.value + "\n"
                
                logger.info(f"Antwort erhalten: {len(result)} Zeichen")
                return result.strip()
            else:
                raise ValueError("Keine Antwort vom Assistant erhalten")
        else:
            error_msg = f"Run fehlgeschlagen mit Status: {run.status}"
            if hasattr(run, 'last_error'):
                error_msg += f", Fehler: {run.last_error}"
            raise ValueError(error_msg)
    
    finally:
        # Lösche die Datei von OpenAI
        try:
            client.files.delete(file_id)
            logger.info(f"OpenAI Datei {file_id} gelöscht")
        except Exception as delete_error:
            logger.error(f"Fehler beim Löschen der OpenAI Datei: {delete_error}") 