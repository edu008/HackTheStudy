"""
Funktionen zur Extraktion von Themen aus der OpenAI-Analyse.
"""
import logging

logger = logging.getLogger(__name__)

def extract_topics_from_analysis(analysis_result):
    """
    Extrahiert Themen und Hauptthema aus dem OpenAI-Analyseergebnis.
    
    Args:
        analysis_result: Das Dictionary mit der OpenAI-Analyse
        
    Returns:
        tuple: (Liste der Themen, Hauptthema)
    """
    try:
        # Hauptthema extrahieren
        main_topic = analysis_result.get('main_topic', 'Unbekanntes Thema')
        
        # Sicherstellen, dass das Hauptthema nicht leer ist
        if not main_topic or main_topic.strip() == "":
            main_topic = "Unbekanntes Thema"
            logger.warning("Leeres Hauptthema in der Analyse gefunden, verwende Standardwert")
        
        logger.info(f"Hauptthema aus der Analyse extrahiert: {main_topic}")
        
        # Themen extrahieren
        topics = analysis_result.get('topics', [])
        
        # Sicherstellen, dass die Themen das richtige Format haben
        valid_topics = []
        for topic in topics:
            # Überprüfe, ob es ein Dictionary ist und die erforderlichen Schlüssel hat
            if isinstance(topic, dict) and 'name' in topic:
                # Stelle sicher, dass "description" vorhanden ist
                if 'description' not in topic:
                    topic['description'] = ""
                valid_topics.append(topic)
            else:
                logger.warning(f"Ungültiges Themenformat ignoriert: {topic}")
        
        # Wenn keine gültigen Themen gefunden wurden, erstelle ein Standardthema
        if not valid_topics:
            logger.warning("Keine gültigen Themen in der Analyse gefunden, erstelle Standardthema")
            valid_topics = [
                {"name": "Allgemeines", "description": "Allgemeine Informationen zum Thema"}
            ]
        
        logger.info(f"{len(valid_topics)} gültige Themen aus der Analyse extrahiert")
        
        return valid_topics, main_topic
        
    except Exception as e:
        logger.error(f"Fehler bei der Themenextraktion: {str(e)}")
        # Fallback für den Fehlerfall
        return [
            {"name": "Verarbeitungsfehler", "description": f"Fehler bei der Themenextraktion: {str(e)}"}
        ], "Fehler" 