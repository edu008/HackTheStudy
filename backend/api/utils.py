import json
import re
import PyPDF2
import docx
from langdetect import detect
import io  # Hinzugefügt für BytesIO
from flask import current_app
import logging
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

def allowed_file(filename):
    allowed_extensions = {'pdf', 'txt', 'docx', 'doc'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def clean_text_for_database(text):
    """
    Bereinigt einen Text, um sicherzustellen, dass er in der Datenbank gespeichert werden kann.
    Entfernt NUL-Zeichen (0x00) und andere problematische Zeichen.
    
    Args:
        text (str): Der zu bereinigende Text
        
    Returns:
        str: Der bereinigte Text
    """
    if not text:
        return ""
    
    try:
        # Entferne Null-Bytes (0x00)
        cleaned_text = text.replace('\x00', '')
        
        # Aggressivere Bereinigung - alle Steuerzeichen außer Zeilenumbrüche und Tabs entfernen
        # Dies verhindert viele Probleme mit exotischen PDF-Formaten
        allowed_control = ['\n', '\r', '\t']
        cleaned_text = ''.join(c for c in cleaned_text if c >= ' ' or c in allowed_control)
        
        # Bereinige Unicode-Escape-Sequenzen, die Probleme verursachen könnten
        cleaned_text = cleaned_text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        
        # Entferne übermäßige Leerzeichen und Zeilenumbrüche
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)  # Mehr als 2 aufeinanderfolgende Zeilenumbrüche reduzieren
        cleaned_text = re.sub(r' {3,}', '  ', cleaned_text)     # Mehr als 2 aufeinanderfolgende Leerzeichen reduzieren
        
        return cleaned_text
    except Exception as e:
        logger.error(f"Fehler bei der Textbereinigung: {str(e)}")
        # Im Fehlerfall einen sicheren leeren String zurückgeben
        return ""

def extract_text_from_file(file_data, file_name):
    """Extrahiert Text aus einer Datei basierend auf dem Dateityp."""
    try:
        if file_name.lower().endswith('.pdf'):
            text = extract_text_from_pdf(file_data)
            
            # Prüfe ob die Antwort bereits einen CORRUPTED_PDF Fehlercode enthält
            if isinstance(text, str) and text.startswith('CORRUPTED_PDF:'):
                return text
                
            # Prüfen, ob Text extrahiert wurde
            if not text or text.strip() == "":
                logger.warning(f"Kein Text aus PDF extrahiert: {file_name}")
                text = "Keine Textdaten konnten aus dieser PDF-Datei extrahiert werden. Es könnte sich um ein Scan-Dokument ohne OCR handeln."
            return text
        elif file_name.lower().endswith('.txt'):
            # Für Text-Dateien, dekodiere mit verschiedenen Encodings
            try:
                text = file_data.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text = file_data.decode('latin-1')
                except UnicodeDecodeError:
                    text = file_data.decode('utf-8', errors='replace')
            
            # Bereinige den Text für die Datenbank
            return clean_text_for_database(text)
        else:
            return "Nicht unterstütztes Dateiformat. Bitte lade PDF- oder TXT-Dateien hoch."
    except Exception as e:
        logger.error(f"Fehler beim Extrahieren des Textes: {str(e)}")
        # Spezielle Behandlung für PdfReadError und ähnliche kritische Fehler
        error_str = str(e)
        if "PdfReadError" in error_str or "Invalid Elementary Object" in error_str:
            return f"CORRUPTED_PDF: {error_str}"
        return f"Fehler beim Extrahieren des Textes: {str(e)}"

def extract_text_from_pdf_safe(file_data):
    """
    Extrahiert Text aus einer PDF-Datei mit maximaler Sicherheit gegen Fehler.
    Verwendet ein mehrstufiges Fallback-System, um mit problematischen PDFs umzugehen.
    """
    # Sammle extrahierten Text von allen Versuchen
    all_extracted_text = []
    
    # Sammle Fehlermeldungen zur späteren Auswertung
    error_messages = []
    
    try:
        # Zuerst versuche die problematischen Null-Bytes zu entfernen
        import re
        safe_data = re.sub(b'\x00', b'', file_data)
        
        # Versuche auch andere problematische Zeichen zu entfernen
        # Besonders wichtig für annotierte PDFs
        for pattern in [b'\x0c', b'\xfe\xff', b'\xff\xfe', b'\\*', b'\\(', b'\\)', b'\\.\\d+\\.']: 
            try:
                safe_data = re.sub(pattern, b' ', safe_data)
            except:
                pass
        
        # 1. Versuch: PyPDF2 mit sicherem Modus
        try:
            import io
            from PyPDF2 import PdfReader
            
            text = ""
            with io.BytesIO(safe_data) as data:
                try:
                    reader = PdfReader(data, strict=False)  # strict=False für bessere Fehlertoleranz
                    for i, page in enumerate(reader.pages):
                        try:
                            extracted = page.extract_text()
                            if extracted:
                                text += extracted + "\n\n"
                                all_extracted_text.append(extracted)
                        except Exception as page_error:
                            error_msg = f"Fehler bei der Extraktion der Seite {i+1}: {str(page_error)}"
                            logger.warning(error_msg)
                            error_messages.append(error_msg)
                            continue
                except Exception as e:
                    error_msg = f"Fehler bei der Extraktion mit PdfReader (1. Versuch): {str(e)}"
                    logger.warning(error_msg)
                    error_messages.append(error_msg)
                    
                    # Prüfe auf bestimmte kritische Fehlertypen, die auf eine korrupte PDF hindeuten
                    if "PdfReadError" in str(e) or "Invalid Elementary Object" in str(e):
                        logger.error(f"Kritischer PDF-Fehler erkannt: {str(e)}")
                        return f"CORRUPTED_PDF: {str(e)}"
        except Exception as e:
            error_msg = f"Allgemeiner Fehler bei PDF-Extraktion (1. Versuch): {str(e)}"
            logger.warning(error_msg)
            error_messages.append(error_msg)
            
            # Prüfe auch hier auf kritische Fehler
            if "PdfReadError" in str(e) or "Invalid Elementary Object" in str(e):
                logger.error(f"Kritischer PDF-Fehler erkannt: {str(e)}")
                return f"CORRUPTED_PDF: {str(e)}"
        
        # Weitere Versuche nur durchführen, wenn keine kritischen Fehler aufgetreten sind
        # und noch kein Text extrahiert wurde
        
        # 2. Versuch: PyPDF2 mit Seitenzugriff über Index
        if not "".join(all_extracted_text).strip():
            try:
                import io
                from PyPDF2 import PdfReader
                
                with io.BytesIO(safe_data) as data:
                    try:
                        reader = PdfReader(data, strict=False)
                        page_count = len(reader.pages)
                        
                        for i in range(page_count):
                            try:
                                # Direkter Zugriff auf die Seite über den Index
                                page = reader.pages[i]
                                try:
                                    extracted = page.extract_text()
                                    if extracted:
                                        all_extracted_text.append(extracted)
                                except Exception as inner_error:
                                    error_msg = f"Fehler beim Extrahieren des Textes der Seite {i+1}: {str(inner_error)}"
                                    logger.warning(error_msg)
                                    error_messages.append(error_msg)
                                    continue
                            except Exception as page_error:
                                error_msg = f"Seite {i+1} konnte nicht geladen werden: {str(page_error)}"
                                logger.warning(error_msg)
                                error_messages.append(error_msg)
                                continue
                    except Exception as e:
                        error_msg = f"Fehler beim Laden des PdfReaders (2. Versuch): {str(e)}"
                        logger.warning(error_msg)
                        error_messages.append(error_msg)
                        
                        # Nochmals auf kritische Fehler prüfen
                        if "PdfReadError" in str(e) or "Invalid Elementary Object" in str(e):
                            logger.error(f"Kritischer PDF-Fehler erkannt im 2. Versuch: {str(e)}")
                            return f"CORRUPTED_PDF: {str(e)}"
            except Exception as e:
                error_msg = f"Allgemeiner Fehler bei PDF-Extraktion (2. Versuch): {str(e)}"
                logger.warning(error_msg)
                error_messages.append(error_msg)
                
                # Und auch hier nochmals auf kritische Fehler prüfen
                if "PdfReadError" in str(e) or "Invalid Elementary Object" in str(e):
                    logger.error(f"Kritischer PDF-Fehler erkannt im 2. Versuch (allgemein): {str(e)}")
                    return f"CORRUPTED_PDF: {str(e)}"
        
        # Weitere Versuche mit anderen Methoden...
        
        # Kombiniere alle extrahierten Texte
        final_text = "\n\n".join([text for text in all_extracted_text if text.strip()])
        
        # Prüfe auf Anzeichen einer korrupten PDF anhand der gesammelten Fehlermeldungen
        critical_error_indicators = [
            "PdfReadError", 
            "Invalid Elementary Object", 
            "Stream has ended unexpectedly",
            "maximum recursion depth exceeded",
            "FloatObject",
            "incorrect startxref"
        ]
        
        error_count = sum(1 for error in error_messages if any(indicator in error for indicator in critical_error_indicators))
        
        # Wenn zu viele kritische Fehler aufgetreten sind, betrachte die PDF als korrupt
        if error_count >= 2:
            logger.error(f"PDF als korrupt erkannt aufgrund von {error_count} kritischen Fehlern")
        # 3. Versuch: Direkter Binärmodus für beschädigte PDFs
        if not "".join(all_extracted_text).strip():
            try:
                import subprocess
                import tempfile
                import os
                
                # Speichere die PDF-Daten temporär
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_file.write(safe_data)
                    temp_file_path = temp_file.name
                
                try:
                    # Versuche pdftotext zu verwenden, falls installiert
                    result = subprocess.run(['pdftotext', temp_file_path, '-'], 
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                           timeout=30, check=False, text=True)
                    
                    if result.returncode == 0 and result.stdout:
                        all_extracted_text.append(result.stdout)
                except (subprocess.SubprocessError, FileNotFoundError):
                    logger.warning("pdftotext nicht verfügbar oder fehlgeschlagen")
                
                # Entferne die temporäre Datei
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            except Exception as e:
                logger.warning(f"Fehler bei der Extraktion mit direktem Binärmodus: {str(e)}")
        
        # 4. Versuch: Nutze PDFMiner bei Bedarf
        if not "".join(all_extracted_text).strip():
            try:
                # Versuche PDFMiner zu importieren
                import io
                try:
                    from pdfminer.high_level import extract_text_to_fp
                    from pdfminer.layout import LAParams
                    
                    output = io.StringIO()
                    with io.BytesIO(safe_data) as fp:
                        laparams = LAParams(char_margin=10.0, line_margin=0.5, word_margin=0.1)
                        extract_text_to_fp(fp, output, laparams=laparams, codec='utf-8')
                        extracted_text = output.getvalue()
                        if extracted_text:
                            all_extracted_text.append(extracted_text)
                except ImportError:
                    logger.warning("PDFMiner nicht verfügbar")
                except Exception as e:
                    logger.warning(f"Fehler bei der Extraktion mit PDFMiner: {str(e)}")
            except Exception as e:
                logger.warning(f"Allgemeiner Fehler bei PDF-Extraktion mit PDFMiner: {str(e)}")
        
        # Kombiniere alle extrahierten Texte
        final_text = "\n\n".join([text for text in all_extracted_text if text.strip()])
        
        # Wenn noch immer kein Text, gib einen klaren Hinweis zurück
        if not final_text.strip():
            return "Der Text konnte aus dieser PDF nicht extrahiert werden. Es könnte sich um eine gescannte PDF ohne OCR, eine beschädigte Datei oder eine stark gesicherte PDF handeln."
        
        # Bereinige den Text für die Datenbank
        return clean_text_for_database(final_text)
    except Exception as e:
        logger.error(f"Kritischer Fehler bei allen PDF-Extraktionsversuchen: {str(e)}")
        return "Fehler beim Extrahieren des Textes aus der PDF-Datei: Die Datei könnte beschädigt sein oder ungewöhnliche Formatierungen enthalten."

def extract_text_from_pdf(file_data):
    """Extrahiert Text aus einer PDF-Datei mit maximaler Sicherheit."""
    try:
        # Versuche erst die neue, sichere Methode
        text = extract_text_from_pdf_safe(file_data)
        
        # Prüfe, ob die sichere Methode einen CORRUPTED_PDF Fehlercode zurückgegeben hat
        if isinstance(text, str) and text.startswith('CORRUPTED_PDF:'):
            return text
            
        if text and text.strip():
            return text
            
        # Wenn das nicht erfolgreich war, probiere die älteren Methoden
        with io.BytesIO(file_data) as data:
            try:
                reader = PdfReader(data)
                text = ""
                
                # Extrahiere Text aus allen Seiten
                for page in reader.pages:
                    text += page.extract_text() + "\n\n"
                
                # Wenn kein Text extrahiert werden konnte, versuche mit PyPDF2
                if not text.strip():
                    logger.warning("Kein Text mit PdfReader extrahiert, verwende PyPDF2 als Fallback.")
                    text = extract_text_from_pdf_fallback(file_data)
                
                # Bereinige den Text für die Datenbank
                return clean_text_for_database(text)
            except Exception as e:
                logger.error(f"Fehler bei der PDF-Textextraktion mit PyPDF2: {str(e)}")
                
                # Spezielle Behandlung für PdfReadError
                error_str = str(e)
                if "PdfReadError" in error_str or "Invalid Elementary Object" in error_str:
                    return f"CORRUPTED_PDF: {error_str}"
                    
                # Versuche den Fallback-Mechanismus
                return extract_text_from_pdf_fallback(file_data)
    except Exception as e:
        logger.error(f"Kritischer Fehler bei der PDF-Extraktion: {str(e)}")
        
        # Auch hier spezielle Behandlung für PdfReadError
        error_str = str(e)
        if "PdfReadError" in error_str or "Invalid Elementary Object" in error_str:
            return f"CORRUPTED_PDF: {error_str}"
            
        return "Die PDF-Datei konnte nicht verarbeitet werden. Mögliche Ursachen: beschädigte Datei, keine Textebene (Scan), oder nicht unterstütztes Format."

def extract_text_from_pdf_fallback(file_data):
    """
    Extrahiert Text aus einer PDF-Datei, wenn die Standardmethode fehlschlägt.
    Dies ist ein Fallback-Mechanismus mit mehreren Versuchen.
    
    Args:
        file_data (bytes): Die PDF-Dateidaten
        
    Returns:
        str: Der extrahierte Text
    """
    try:
        # Methode 1: Mit BytesIO und direktem PdfReader
        with io.BytesIO(file_data) as data:
            reader = PdfReader(data)
            text = ""
            for page in reader.pages:
                try:
                    # Versuche Text zu extrahieren und fange spezifische Fehler ab
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n\n"
                except Exception as e:
                    logger.warning(f"Fehler bei der Textextraktion einer Seite: {str(e)}")
                    continue
        
        # Wenn keine Textextraktion erfolgreich war, versuche andere Methoden
        if not text.strip():
            logger.warning("Fallback 1 konnte keinen Text extrahieren, versuche Fallback 2")
            
            # Methode 2: Direkter Binärzugriff - entferne explizit Null-Bytes
            try:
                import re
                import binascii
                
                # Entferne alle Null-Bytes und andere nicht-druckbare Zeichen
                cleaned_data = re.sub(b'[\x00]', b'', file_data)
                
                # Versuche erneut die Extraktion
                with io.BytesIO(cleaned_data) as clean_data:
                    reader = PdfReader(clean_data)
                    for page in reader.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text += extracted + "\n\n"
            except Exception as e:
                logger.warning(f"Fallback 2 fehlgeschlagen: {str(e)}")
        
        # Bereinige den resultierenden Text
        return clean_text_for_database(text)
    
    except Exception as e:
        logger.error(f"Alle PDF-Extraktionsversuche fehlgeschlagen: {str(e)}")
        return f"Text konnte nicht extrahiert werden: {str(e)}"

def detect_language(text):
    try:
        lang = detect(text[:500])  # Begrenze auf 500 Zeichen für Effizienz
        return 'de' if lang == 'de' else 'en'
    except Exception:
        return 'en'

import random
import time
from functools import lru_cache
import hashlib

# Cache für OpenAI-Antworten
_response_cache = {}

def query_chatgpt(prompt, client, system_content=None, temperature=0.7, max_retries=5, use_cache=True):
    """
    Sendet eine Anfrage an die OpenAI API mit exponentiellem Backoff bei Ratenlimit-Fehlern.
    
    Args:
        prompt: Der Prompt-Text für die Anfrage
        client: Der OpenAI-Client
        system_content: Optionaler System-Prompt
        temperature: Temperatur für die Antwortgenerierung (0.0-1.0)
        max_retries: Maximale Anzahl von Wiederholungsversuchen
        use_cache: Ob der Cache verwendet werden soll (default: True)
        
    Returns:
        Die Antwort der API oder eine Fehlermeldung
    """
    # DEBUG: Ausführliches Logging für Docker
    print("\n\n==================================================")
    print("OPENAI DEBUG: ANFRAGE DETAILS")
    print("==================================================")
    print(f"SYSTEM PROMPT: {system_content[:300]}..." if system_content and len(system_content) > 300 else f"SYSTEM PROMPT: {system_content}")
    print(f"USER PROMPT (gekürzt): {prompt[:300]}..." if len(prompt) > 300 else f"USER PROMPT: {prompt}")
    print(f"PARAMETER: model=gpt-4o, temperature={temperature}, max_tokens=4000")
    print("==================================================\n\n")
    
    # Wenn Caching aktiviert ist, erstelle einen Hash-Schlüssel für den Cache
    if use_cache:
        # Erstelle einen Hash aus dem Prompt und dem System-Content
        cache_key = hashlib.md5((prompt + str(system_content) + str(temperature)).encode()).hexdigest()
        
        # Prüfe, ob die Antwort bereits im Cache ist
        if cache_key in _response_cache:
            print(f"Cache hit for prompt: {prompt[:50]}...")
            return _response_cache[cache_key]
    
    retry_count = 0
    base_delay = 1  # Sekunden
    
    while retry_count < max_retries:
        try:
            messages = []
            if system_content:
                messages.append({"role": "system", "content": system_content})
            else:
                messages.append({"role": "system", "content": "You are a helpful assistant that provides concise, accurate information."})
            messages.append({"role": "user", "content": prompt})
            
            # Hier einen Mock-Response zurückgeben, wenn wir zu viele Rate-Limits bekommen
            if retry_count >= 3:
                print(f"Using fallback response after {retry_count} retries")
                mock_response = generate_mock_response(prompt, system_content)
                
                # Debug: Logging der Fallback-Antwort
                print("\n\n==================================================")
                print("OPENAI DEBUG: FALLBACK ANTWORT VERWENDET")
                print("==================================================")
                print(f"ANTWORT (gekürzt): {mock_response[:300]}..." if len(mock_response) > 300 else f"ANTWORT: {mock_response}")
                print("==================================================\n\n")
                
                # Speichere die Antwort im Cache, wenn Caching aktiviert ist
                if use_cache:
                    _response_cache[cache_key] = mock_response
                
                return mock_response
            
            # Debug: API-Aufruf loggen
            print(f"\nDEBUG: Sending API request (attempt {retry_count+1}/{max_retries})")
            
            response = client.chat.completions.create(
                model=current_app.config.get('OPENAI_MODEL', 'gpt-4o'),
                messages=messages,
                temperature=temperature,
                max_tokens=4000
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Debug: Erfolgreiche Antwort loggen
            print("\n\n==================================================")
            print("OPENAI DEBUG: ERFOLGREICHE ANTWORT")
            print("==================================================")
            print(f"ANTWORT (gekürzt): {response_text[:300]}..." if len(response_text) > 300 else f"ANTWORT: {response_text}")
            print("==================================================\n\n")
            
            # Speichere die Antwort im Cache, wenn Caching aktiviert ist
            if use_cache:
                _response_cache[cache_key] = response_text
            
            return response_text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and retry_count < max_retries - 1:
                # Exponentielles Backoff
                delay = base_delay * (2 ** retry_count)
                # Füge etwas Zufälligkeit hinzu, um "Thundering Herd" zu vermeiden
                jitter = random.uniform(0, 0.1 * delay)
                sleep_time = delay + jitter
                
                # Log the retry attempt
                print(f"OpenAI API rate limit hit, retrying in {sleep_time:.2f} seconds... (Attempt {retry_count + 1}/{max_retries})")
                
                time.sleep(sleep_time)
                retry_count += 1
            else:
                # Bei anderen Fehlern oder wenn max_retries erreicht ist
                print(f"Error querying OpenAI API: {error_str}, using fallback response")
                
                # Debug: Fehler ausführlich loggen
                print("\n\n==================================================")
                print("OPENAI DEBUG: FEHLER")
                print("==================================================")
                print(f"FEHLER: {error_str}")
                print("FALLBACK WIRD VERWENDET")
                print("==================================================\n\n")
                
                mock_response = generate_mock_response(prompt, system_content)
                
                # Speichere die Antwort im Cache, wenn Caching aktiviert ist
                if use_cache:
                    _response_cache[cache_key] = mock_response
                
                return mock_response
    
    # Nach allen Wiederholungsversuchen verwenden wir eine Mock-Antwort
    print("Maximum retries exceeded, using fallback response")
    mock_response = generate_mock_response(prompt, system_content)
    
    # Debug: Maximale Wiederholungen überschritten
    print("\n\n==================================================")
    print("OPENAI DEBUG: MAX RETRIES ÜBERSCHRITTEN")
    print("==================================================")
    print("FALLBACK WIRD VERWENDET")
    print(f"ANTWORT (gekürzt): {mock_response[:300]}..." if len(mock_response) > 300 else f"ANTWORT: {mock_response}")
    print("==================================================\n\n")
    
    # Speichere die Antwort im Cache, wenn Caching aktiviert ist
    if use_cache:
        _response_cache[cache_key] = mock_response
    
    return mock_response

def generate_mock_response(prompt, system_content=None, file_name=None):
    """
    Generiert eine intelligentere Mock-Antwort basierend auf dem Prompt, dem System-Content und optional dem Dateinamen.
    Dies wird verwendet, wenn OpenAI-API-Anfragen fehlschlagen oder das Rate-Limit erreicht ist.
    """
    # Extrahiere Hinweise aus dem Dateinamen
    topic_hints = {}
    if file_name:
        file_name = file_name.lower()
        if "nsa" in file_name or "network" in file_name or "security" in file_name:
            topic_hints = {
                "main_topic": "Network Security Analysis",
                "subtopics": [
                    {"name": "Vulnerability Assessment", "child_topics": ["Scanning Tools", "Risk Scoring", "Remediation"]},
                    {"name": "Intrusion Detection", "child_topics": ["Signature Detection", "Anomaly Detection", "SIEM Tools"]},
                    {"name": "Encryption Protocols", "child_topics": ["Symmetric Encryption", "Asymmetric Encryption", "TLS/SSL"]},
                    {"name": "Authentication Methods", "child_topics": ["Multi-factor Authentication", "Biometrics", "Zero Trust"]}
                ],
                "key_terms": [
                    {"term": "Firewall", "definition": "A security system that monitors and controls incoming and outgoing network traffic."},
                    {"term": "IDS/IPS", "definition": "Intrusion Detection/Prevention Systems that monitor networks for suspicious activities."},
                    {"term": "VPN", "definition": "Virtual Private Network that extends a private network across public networks."}
                ]
            }
        elif "program" in file_name or "coding" in file_name or "algorithm" in file_name:
            topic_hints = {
                "main_topic": "Programming Fundamentals",
                "subtopics": [
                    {"name": "Data Structures", "child_topics": ["Arrays", "Linked Lists", "Trees", "Graphs"]},
                    {"name": "Algorithms", "child_topics": ["Sorting", "Searching", "Dynamic Programming", "Greedy Algorithms"]},
                    {"name": "Programming Paradigms", "child_topics": ["Procedural", "Object-Oriented", "Functional", "Event-Driven"]}
                ],
                "key_terms": [
                    {"term": "Complexity", "definition": "A measure of the resources required for an algorithm to run."},
                    {"term": "Recursion", "definition": "A programming technique where a function calls itself."},
                    {"term": "Object", "definition": "An instance of a class that encapsulates data and behavior."}
                ]
            }
        elif "math" in file_name or "calculus" in file_name or "algebra" in file_name:
            topic_hints = {
                "main_topic": "Advanced Mathematics",
                "subtopics": [
                    {"name": "Calculus", "child_topics": ["Differentiation", "Integration", "Limits", "Series"]},
                    {"name": "Linear Algebra", "child_topics": ["Matrices", "Vector Spaces", "Eigenvalues", "Transformations"]},
                    {"name": "Probability Theory", "child_topics": ["Distributions", "Random Variables", "Bayesian Statistics"]}
                ],
                "key_terms": [
                    {"term": "Derivative", "definition": "The rate of change of a function with respect to a variable."},
                    {"term": "Matrix", "definition": "A rectangular array of numbers arranged in rows and columns."},
                    {"term": "Probability Distribution", "definition": "A function that gives the probabilities of occurrence of different outcomes."}
                ]
            }
    
    # Wenn keine Hinweise gefunden wurden, verwende einen generischen Ansatz
    if not topic_hints:
        topic_hints = {
            "main_topic": "Academic Study Methods",
            "subtopics": [
                {"name": "Effective Learning Strategies", "child_topics": ["Spaced Repetition", "Active Recall", "Feynman Technique"]},
                {"name": "Time Management", "child_topics": ["Pomodoro Technique", "Prioritization", "Deep Work Sessions"]},
                {"name": "Information Organization", "child_topics": ["Mind Mapping", "Cornell Note-Taking", "Outlining Methods"]},
                {"name": "Critical Thinking", "child_topics": ["Argument Analysis", "Bias Identification", "Socratic Questioning"]}
            ],
            "key_terms": [
                {"term": "Metacognition", "definition": "The awareness and understanding of one's own thought processes."},
                {"term": "Elaborative Interrogation", "definition": "Asking 'why' and 'how' questions to deepen understanding."},
                {"term": "Cognitive Load", "definition": "The total amount of mental effort used in working memory."}
            ]
        }
    
    # Flashcard-Anfrage
    if "generate" in prompt.lower() and "flashcard" in prompt.lower():
        flashcards = []
        for subtopic in topic_hints["subtopics"]:
            # Generiere Flashcards für jedes Unterthema
            flashcards.append({
                "question": f"What are the key components of {subtopic['name']}?",
                "answer": f"The key components include {', '.join(subtopic['child_topics'])}."
            })
            
            # Generiere zusätzliche Flashcards für einige Unterunterthemen
            for child_topic in subtopic['child_topics'][:2]:  # Begrenze auf die ersten zwei Kinder
                flashcards.append({
                    "question": f"Explain the concept of {child_topic} in the context of {subtopic['name']}.",
                    "answer": f"{child_topic} is an important aspect of {subtopic['name']} that helps to structure and organize information effectively."
                })
        
        # Füge einige Flashcards für Schlüsselbegriffe hinzu
        for term_info in topic_hints["key_terms"][:3]:  # Begrenze auf die ersten drei Begriffe
            flashcards.append({
                "question": f"Define the term: {term_info['term']}",
                "answer": term_info['definition']
            })
            
        return json.dumps(flashcards[:10])  # Begrenze auf 10 Flashcards
    
    # Test-Fragen-Anfrage
    elif "generate" in prompt.lower() and "question" in prompt.lower():
        questions = []
        for subtopic in topic_hints["subtopics"]:
            options = subtopic['child_topics'] + [f"None of the above"]
            questions.append({
                "text": f"Which of the following is NOT a component of {subtopic['name']}?",
                "options": options,
                "correct": len(options) - 1,  # "None of the above" ist die letzte Option
                "explanation": f"All of the listed items except 'None of the above' are components of {subtopic['name']}."
            })
        
        # Generiere einige Fragen auf Grundlage der Schlüsselbegriffe
        for term_info in topic_hints["key_terms"][:2]:
            questions.append({
                "text": f"What is the correct definition of {term_info['term']}?",
                "options": [
                    term_info['definition'],
                    f"A technique for visualizing complex data structures",
                    f"A method for organizing information in a hierarchical format",
                    f"A strategy for improving memory retention"
                ],
                "correct": 0,  # Die richtige Definition ist die erste Option
                "explanation": f"The term {term_info['term']} is correctly defined as: {term_info['definition']}"
            })
            
        return json.dumps(questions[:5])  # Begrenze auf 5 Fragen
    
    # Analyse-Anfrage
    elif "analyze" in prompt.lower() or "extract" in prompt.lower():
        return json.dumps({
            "main_topic": topic_hints["main_topic"],
            "subtopics": topic_hints["subtopics"],
            "estimated_flashcards": 15,
            "estimated_questions": 8,
            "key_terms": topic_hints["key_terms"],
            "content_type": "lecture"
        })
    
    # Fallback für andere Anfragen
    else:
        return "Could not generate response from OpenAI API. Please try again later."

def analyze_content(text, client, language='en'):
    system_content = (
        "You are an expert in educational content analysis with a specialization in creating hierarchical knowledge structures."
        if language != 'de' else
        "Sie sind ein Experte für die Analyse von Bildungsinhalten mit einer Spezialisierung auf die Erstellung hierarchischer Wissensstrukturen."
    )
    
    prompt = (
        """
        Analyze the following academic text and extract a hierarchical knowledge structure with these components:
        
        1. MAIN TOPIC: The primary subject of the text (a concise phrase, max 5 words)
        
        2. SUBTOPICS: 3-7 major concepts or areas within the main topic
        
        3. CHILD SUBTOPICS: For each subtopic, provide 2-4 more specific concepts (these are children of the subtopics)
        
        4. FLASHCARDS: Estimate how many flashcards would be useful (between 10-30)
        
        5. QUESTIONS: Estimate how many test questions would be useful (between 5-15)
        
        6. KEY TERMS: Extract 5-10 important technical terms or concepts with their definitions
        
        7. CONTENT TYPE: Identify the type (e.g., 'lecture', 'textbook', 'scientific paper', 'technical documentation')
        
        Return your analysis in valid JSON format with these keys:
        - main_topic (string)
        - subtopics (array of objects with 'name' and 'child_topics' keys, where 'child_topics' is an array of strings)
        - estimated_flashcards (number)
        - estimated_questions (number)
        - key_terms (array of objects with 'term' and 'definition' keys)
        - content_type (string)
        
        Text to analyze:
        """
        if language != 'de' else
        """
        Analysieren Sie den folgenden akademischen Text und extrahieren Sie eine hierarchische Wissensstruktur mit diesen Komponenten:
        
        1. HAUPTTHEMA: Das primäre Thema des Textes (ein prägnanter Ausdruck, max. 5 Wörter)
        
        2. UNTERTHEMEN: 3-7 wichtige Konzepte oder Bereiche innerhalb des Hauptthemas
        
        3. UNTERUNTERTHEMEN: Für jedes Unterthema 2-4 spezifischere Konzepte (diese sind Kinder der Unterthemen)
        
        4. KARTEIKARTEN: Schätzen Sie, wie viele Karteikarten nützlich wären (zwischen 10-30)
        
        5. FRAGEN: Schätzen Sie, wie viele Testfragen nützlich wären (zwischen 5-15)
        
        6. SCHLÜSSELBEGRIFFE: Extrahieren Sie 5-10 wichtige Fachbegriffe oder Konzepte mit ihren Definitionen
        
        7. INHALTSTYP: Identifizieren Sie den Typ (z.B. 'Vorlesung', 'Lehrbuch', 'wissenschaftlicher Artikel', 'technische Dokumentation')
        
        Geben Sie Ihre Analyse im gültigen JSON-Format mit diesen Schlüsseln zurück:
        - main_topic (string)
        - subtopics (Array von Objekten mit den Schlüsseln 'name' und 'child_topics', wobei 'child_topics' ein Array von Strings ist)
        - estimated_flashcards (Zahl)
        - estimated_questions (Zahl)
        - key_terms (Array von Objekten mit den Schlüsseln 'term' und 'definition')
        - content_type (string)
        
        Zu analysierender Text:
        """
    )
    
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"
    
    response = query_chatgpt(prompt + text, client, system_content)
    
    try:
        result = json.loads(response)
        expected_keys = ['main_topic', 'subtopics', 'estimated_flashcards', 'estimated_questions', 'key_terms', 'content_type']
        for key in expected_keys:
            if key not in result:
                if key == 'subtopics':
                    result[key] = []
                elif key == 'key_terms':
                    result[key] = []
                elif key == 'main_topic':
                    result[key] = "Unknown Topic"
                elif key == 'content_type':
                    result[key] = "unknown"
                else:
                    result[key] = 0
        return result
    except json.JSONDecodeError:
        # Fallback when JSON parsing fails
        print("JSON parsing failed, using regex extraction")
        main_topic_match = re.search(r'"main_topic"\s*:\s*"([^"]+)"', response)
        subtopics_match = re.search(r'"subtopics"\s*:\s*\[(.*?)\]', response, re.DOTALL)
        flashcards_match = re.search(r'"estimated_flashcards"\s*:\s*(\d+)', response)
        questions_match = re.search(r'"estimated_questions"\s*:\s*(\d+)', response)
        
        main_topic = main_topic_match.group(1) if main_topic_match else "Unknown Topic"
        subtopics_str = subtopics_match.group(1) if subtopics_match else ""
        
        # Simplified regex-based extraction
        fallback_subtopics = []
        try:
            # Extract objects from the subtopics array
            subtopic_objects = re.findall(r'{[^}]+}', subtopics_str)
            for obj in subtopic_objects:
                name_match = re.search(r'"name"\s*:\s*"([^"]+)"', obj)
                if name_match:
                    name = name_match.group(1)
                    child_topics = []
                    child_topics_match = re.search(r'"child_topics"\s*:\s*\[(.*?)\]', obj, re.DOTALL)
                    if child_topics_match:
                        child_topics_str = child_topics_match.group(1)
                        child_topics = [topic.strip(' "\'') for topic in re.findall(r'"([^"]+)"', child_topics_str)]
                    fallback_subtopics.append({"name": name, "child_topics": child_topics})
        except:
            # If regex extraction fails, use a very simple approach
            subtopics = [s.strip(' "\'') for s in subtopics_str.split(',') if s.strip(' "\'')]
            fallback_subtopics = [{"name": topic, "child_topics": []} for topic in subtopics]
        
        estimated_flashcards = int(flashcards_match.group(1)) if flashcards_match else 15
        estimated_questions = int(questions_match.group(1)) if questions_match else 8
        
        return {
            'main_topic': main_topic,
            'subtopics': fallback_subtopics,
            'estimated_flashcards': estimated_flashcards,
            'estimated_questions': estimated_questions,
            'key_terms': [],
            'content_type': "unknown"
        }

def filter_visual_references(items, is_flashcard=True):
    """Filtert Fragen oder Antworten mit Bezug zu visuellen Hilfsmitteln."""
    visual_keywords = ['diagram', 'figure', 'table', 'graph', 'chart', 'image', 'illustration', 'visual']
    if is_flashcard:
        return [
            item for item in items
            if all(keyword not in item.get('question', '').lower() and keyword not in item.get('answer', '').lower()
                   for keyword in visual_keywords)
        ]
    else:
        return [
            item for item in items
            if all(keyword not in item.get('text', '').lower() and keyword not in ' '.join(item.get('options', [])).lower()
                   and keyword not in item.get('explanation', '').lower() for keyword in visual_keywords)
        ]


def generate_flashcards(text, client, analysis=None, existing_flashcards=None, language='en'):
    system_content = (
        """
        You are an expert in creating educational flashcards. Your task is to generate COMPLETELY NEW, ORIGINAL flashcards that are FUNDAMENTALLY DIFFERENT from any existing ones.
        
        CRITICAL INSTRUCTIONS:
        - IGNORE the existing flashcards completely except to ensure you don't create anything similar.
        - DO NOT use the existing flashcards as templates or inspiration.
        - CREATE ENTIRELY NEW content based on the subtopics provided.
        - INVENT new scenarios, examples, and applications related to the subtopics.
        - Each flashcard must cover a DIFFERENT ASPECT of the subject matter than both existing flashcards AND other new flashcards you create.
        - Use DIFFERENT question formats, structures, and approaches for each flashcard.
        - If you've created a definition-style question, don't create another one. If you've created a comparison question, don't create another one.
        - VARY your language patterns, sentence structures, and terminology significantly.
        - FOCUS on creating flashcards that explore the subtopics from completely different angles and perspectives.
        - Base your questions and answers on the text provided, but if the text lacks specific information, invent plausible, hypothetical scenarios that are thematically consistent with the main topic and subtopics.
        - Ensure that every question has a clear, informative answer. Do NOT return answers like "Unknown" or "Not provided in the text."
        - Do NOT generate any questions or answers that mention, imply, refer to, or depend on diagrams, figures, tables, graphs, charts, images, illustrations, or any other visual aids.
        - Every question and answer MUST be fully standalone, self-contained, and understandable without any visual context or additional resources beyond the provided text.
        """
        if language != 'de' else
        """
        Sie sind ein Experte für die Erstellung von Lernkarteikarten. Ihre Aufgabe ist es, KOMPLETT NEUE, ORIGINALE Karteikarten zu erstellen, die sich GRUNDLEGEND von allen vorhandenen unterscheiden.
        
        KRITISCHE ANWEISUNGEN:
        - IGNORIEREN Sie die vorhandenen Karteikarten vollständig, außer um sicherzustellen, dass Sie nichts Ähnliches erstellen.
        - Verwenden Sie die vorhandenen Karteikarten NICHT als Vorlagen oder Inspiration.
        - ERSTELLEN Sie VÖLLIG NEUE Inhalte basierend auf den bereitgestellten Unterthemen.
        - ERFINDEN Sie neue Szenarien, Beispiele und Anwendungen im Zusammenhang mit den Unterthemen.
        - Jede Karteikarte muss einen ANDEREN ASPEKT des Themas abdecken als sowohl die vorhandenen Karteikarten ALS AUCH andere neue Karteikarten, die Sie erstellen.
        - Verwenden Sie für jede Karteikarte UNTERSCHIEDLICHE Frageformate, Strukturen und Ansätze.
        - Wenn Sie eine Definitionsfrage erstellt haben, erstellen Sie keine weitere. Wenn Sie eine Vergleichsfrage erstellt haben, erstellen Sie keine weitere.
        - VARIIEREN Sie Ihre Sprachmuster, Satzstrukturen und Terminologie erheblich.
        - KONZENTRIEREN Sie sich darauf, Karteikarten zu erstellen, die die Unterthemen aus völlig verschiedenen Blickwinkeln und Perspektiven untersuchen.
        - Stützen Sie Ihre Fragen und Antworten auf den bereitgestellten Text, aber wenn der Text keine spezifischen Informationen enthält, erfinden Sie plausible, hypothetische Szenarien, die thematisch mit dem Hauptthema und den Unterthemen übereinstimmen.
        - Stellen Sie sicher, dass jede Frage eine klare, informative Antwort hat. Geben Sie KEINE Antworten wie "Unbekannt" oder "Nicht im Text angegeben" zurück.
        - Erstellen Sie KEINE Fragen oder Antworten, die Diagramme, Abbildungen, Tabellen, Grafiken, Diagramme, Bilder, Illustrationen oder andere visuelle Hilfsmittel erwähnen, andeuten, darauf verweisen oder davon abhängen.
        - Jede Frage und Antwort MUSS vollständig eigenständig, in sich geschlossen und verständlich sein, ohne jeglichen visuellen Kontext oder zusätzliche Ressourcen außer dem bereitgestellten Text.
        """
    )

    prompt = (
        """
        Create COMPLETELY NEW and ORIGINAL flashcards for the following material. Each flashcard should have a question and an answer.
        
        IMPORTANT INSTRUCTIONS:
        - FOCUS on the subtopics provided and create flashcards that explore different aspects of these subtopics.
        - CREATE flashcards that are COMPLETELY DIFFERENT from any existing ones in content, structure, and approach.
        - INVENT new scenarios, examples, and applications related to the subtopics.
        - USE a wide variety of question types: definitions, comparisons, applications, analyses, evaluations, etc.
        - VARY your language patterns, sentence structures, and terminology significantly between flashcards.
        - DO NOT follow patterns from existing flashcards - create entirely new patterns.
        - Base questions and answers on key concepts in the text. If the text does not provide enough information to answer a question, invent a plausible, hypothetical scenario that aligns with the main topic and subtopics to provide a clear, informative answer.
        - Do NOT return answers like "Unknown" or "Not provided in the text." Instead, create a reasonable scenario based on the themes of the text.
        - Do NOT include any questions or answers that mention, imply, or rely on diagrams, figures, tables, graphs, charts, images, illustrations, or any other visual aids.
        - Answers must be precise, informative, and fully self-contained, with NO references to visual elements or external context.
        - Format your response as a JSON array of objects with the keys "question" and "answer".
        
        EXAMPLES OF DIFFERENT QUESTION TYPES TO USE (create your own, don't copy these):
        - "How would [concept] be applied in [novel scenario]?"
        - "Compare and contrast [concept A] with [concept B] in terms of [aspect]."
        - "What would be the implications of [hypothetical scenario related to subtopic]?"
        - "Explain the relationship between [concept A] and [concept B] in the context of [subtopic]."
        - "What are three key factors that influence [process related to subtopic]?"
        """
        if language != 'de' else
        """
        Erstellen Sie KOMPLETT NEUE und ORIGINALE Karteikarten für das folgende Material. Jede Karteikarte sollte eine Frage und eine Antwort enthalten.
        
        WICHTIGE ANWEISUNGEN:
        - KONZENTRIEREN Sie sich auf die bereitgestellten Unterthemen und erstellen Sie Karteikarten, die verschiedene Aspekte dieser Unterthemen untersuchen.
        - ERSTELLEN Sie Karteikarten, die sich in Inhalt, Struktur und Ansatz VOLLSTÄNDIG von allen vorhandenen unterscheiden.
        - ERFINDEN Sie neue Szenarien, Beispiele und Anwendungen im Zusammenhang mit den Unterthemen.
        - VERWENDEN Sie eine große Vielfalt an Fragetypen: Definitionen, Vergleiche, Anwendungen, Analysen, Bewertungen usw.
        - VARIIEREN Sie Ihre Sprachmuster, Satzstrukturen und Terminologie erheblich zwischen den Karteikarten.
        - Folgen Sie NICHT den Mustern vorhandener Karteikarten - erstellen Sie völlig neue Muster.
        - Stützen Sie Fragen und Antworten auf Schlüsselkonzepte im Text. Wenn der Text nicht genügend Informationen zur Beantwortung einer Frage bietet, erfinden Sie ein plausibles, hypothetisches Szenario, das mit dem Hauptthema und den Unterthemen übereinstimmt, um eine klare, informative Antwort zu geben.
        - Geben Sie KEINE Antworten wie "Unbekannt" oder "Nicht im Text angegeben" zurück. Erfinden Sie stattdessen ein vernünftiges Szenario basierend auf den Themen des Textes.
        - Fügen Sie KEINE Fragen oder Antworten hinzu, die Diagramme, Abbildungen, Tabellen, Grafiken, Diagramme, Bilder, Illustrationen oder andere visuelle Hilfsmittel erwähnen, andeuten oder darauf angewiesen sind.
        - Die Antworten müssen präzise, informativ und vollständig eigenständig sein, OHNE Verweise auf visuelle Elemente oder externen Kontext.
        - Formatieren Sie Ihre Antwort als JSON-Array mit Objekten, die die Schlüssel "question" und "answer" enthalten.
        
        BEISPIELE FÜR VERSCHIEDENE FRAGETYPEN (erstellen Sie Ihre eigenen, kopieren Sie diese nicht):
        - "Wie würde [Konzept] in [neuartiges Szenario] angewendet werden?"
        - "Vergleichen und kontrastieren Sie [Konzept A] mit [Konzept B] in Bezug auf [Aspekt]."
        - "Was wären die Auswirkungen von [hypothetisches Szenario im Zusammenhang mit Unterthema]?"
        - "Erklären Sie die Beziehung zwischen [Konzept A] und [Konzept B] im Kontext von [Unterthema]."
        - "Was sind drei Schlüsselfaktoren, die [Prozess im Zusammenhang mit Unterthema] beeinflussen?"
        """
    )

    if analysis:
        prompt += (
            f"\n\nMain topic: {analysis.get('main_topic', '')}\nSubtopics: {', '.join([subtopic['name'] if isinstance(subtopic, dict) and 'name' in subtopic else str(subtopic) for subtopic in analysis.get('subtopics', [])])}\n"
            if language != 'de' else
            f"\n\nHauptthema: {analysis.get('main_topic', '')}\nUnterthemen: {', '.join([subtopic['name'] if isinstance(subtopic, dict) and 'name' in subtopic else str(subtopic) for subtopic in analysis.get('subtopics', [])])}\n"
        )

    if existing_flashcards:
        prompt += (
            "\n\n### EXISTING FLASHCARDS (DO NOT REUSE THESE EXACT QUESTIONS OR CREATE SIMILAR ONES) ###\n"
            if language != 'de' else
            "\n\n### BEREITS VORHANDENE KARTEIKARTEN (VERWENDEN SIE DIESE GENAUEN FRAGEN NICHT ODER ERSTELLEN SIE ÄHNLICHE) ###\n"
        )
        for i, f in enumerate(existing_flashcards):
            prompt += f"{i+1}. Question: {f.get('question', '')}\n   Answer: {f.get('answer', '')}\n"
        prompt += (
            "\nCreate COMPLETELY NEW flashcards with entirely different structures, numbers, contexts, and topics, avoiding any similarity to the above existing flashcards.\n"
            if language != 'de' else
            "\nErstellen Sie KOMPLETT NEUE Karteikarten mit völlig anderen Strukturen, Zahlen, Kontexten und Themen, und vermeiden Sie jede Ähnlichkeit mit den oben genannten vorhandenen Karteikarten.\n"
        )

    num_flashcards = min(analysis.get('estimated_flashcards', 10), 15) if analysis else 10
    prompt += (
        f"\nCreate {num_flashcards} flashcards for the following text:\n\n"
        if language != 'de' else
        f"\nErstellen Sie {num_flashcards} Karteikarten für den folgenden Text:\n\n"
    )

    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"

    # Erhöhe die Temperatur für mehr Kreativität
    response = query_chatgpt(prompt + text, client, system_content, temperature=0.9)

    try:
        flashcards = json.loads(response)
        if not isinstance(flashcards, list):
            raise ValueError("Response is not a list")
        valid_flashcards = [fc for fc in flashcards if isinstance(fc, dict) and 'question' in fc and 'answer' in fc]
        return filter_visual_references(valid_flashcards, is_flashcard=True)
    except (json.JSONDecodeError, ValueError):
        pattern = r'(?:Q:|"question":\s*")(.*?)(?:"\s*,|\n\s*A:)(?:\s*"answer":\s*"|\s*)(.*?)(?:"\s*}|(?=\n\s*Q:|$))'
        matches = re.findall(pattern, response, re.DOTALL)
        flashcards = [{"question": q.strip().strip('"'), "answer": a.strip().strip('"')} for q, a in matches if q and a]
        return filter_visual_references(flashcards, is_flashcard=True) if flashcards else [{"question": "Could not generate flashcards", "answer": "Please try again"}]


# ... (andere Funktionen wie allowed_file, extract_text_from_file, etc. bleiben gleich)

def generate_test_questions(text, client, analysis=None, existing_questions_list=None, language='en'):
    system_content = (
        """
        You are an expert in creating exam questions. Your task is to create COMPLETELY NEW and ORIGINAL multiple-choice test questions that are FUNDAMENTALLY DIFFERENT from any existing questions.
        
        CRITICAL INSTRUCTIONS:
        - IGNORE the existing questions completely except to ensure you don't create anything similar.
        - DO NOT use the existing questions as templates or inspiration.
        - CREATE ENTIRELY NEW content based on the subtopics provided.
        - INVENT new scenarios, examples, and applications related to the subtopics.
        - Each question must cover a DIFFERENT ASPECT of the subject matter than both existing questions AND other new questions you create.
        - Use DIFFERENT question formats, structures, and approaches for each question.
        - If you've created a factual recall question, don't create another one. If you've created an application question, don't create another one.
        - VARY your language patterns, sentence structures, and terminology significantly.
        - FOCUS on creating questions that explore the subtopics from completely different angles and perspectives.
        - Base your questions and answers on the text provided, but if the text lacks specific information, invent plausible, hypothetical scenarios that are thematically consistent with the main topic and subtopics.
        - Ensure that every question has a clear, informative answer with a correct option. Do NOT return answers or explanations like "Unknown" or "Not provided in the text."
        - Do NOT generate any questions, options, or explanations that mention, imply, refer to, or depend on diagrams, figures, tables, graphs, charts, images, illustrations, or any other visual aids.
        - Every question, its options, and explanation MUST be fully standalone, self-contained, and understandable without any visual context or additional resources beyond the provided text.
        - The "correct" value MUST be an integer (0-3) representing the index of the correct option in the "options" array, NOT the text of the answer.
        """
        if language != 'de' else
        """
        Sie sind ein Experte für die Erstellung von Testfragen. Ihre Aufgabe ist es, KOMPLETT NEUE und ORIGINALE Multiple-Choice-Fragen zu erstellen, die sich GRUNDLEGEND von allen vorhandenen Fragen unterscheiden.
        
        KRITISCHE ANWEISUNGEN:
        - IGNORIEREN Sie die vorhandenen Fragen vollständig, außer um sicherzustellen, dass Sie nichts Ähnliches erstellen.
        - Verwenden Sie die vorhandenen Fragen NICHT als Vorlagen oder Inspiration.
        - ERSTELLEN Sie VÖLLIG NEUE Inhalte basierend auf den bereitgestellten Unterthemen.
        - ERFINDEN Sie neue Szenarien, Beispiele und Anwendungen im Zusammenhang mit den Unterthemen.
        - Jede Frage muss einen ANDEREN ASPEKT des Themas abdecken als sowohl die vorhandenen Fragen ALS AUCH andere neue Fragen, die Sie erstellen.
        - Verwenden Sie für jede Frage UNTERSCHIEDLICHE Frageformate, Strukturen und Ansätze.
        - Wenn Sie eine Faktenwissensfrage erstellt haben, erstellen Sie keine weitere. Wenn Sie eine Anwendungsfrage erstellt haben, erstellen Sie keine weitere.
        - VARIIEREN Sie Ihre Sprachmuster, Satzstrukturen und Terminologie erheblich.
        - KONZENTRIEREN Sie sich darauf, Fragen zu erstellen, die die Unterthemen aus völlig verschiedenen Blickwinkeln und Perspektiven untersuchen.
        - Stützen Sie Ihre Fragen und Antworten auf den bereitgestellten Text, aber wenn der Text keine spezifischen Informationen enthält, erfinden Sie plausible, hypothetische Szenarien, die thematisch mit dem Hauptthema und den Unterthemen übereinstimmen.
        - Stellen Sie sicher, dass jede Frage eine klare, informative Antwort mit einer korrekten Option hat. Geben Sie KEINE Antworten oder Erklärungen wie "Unbekannt" oder "Nicht im Text angegeben" zurück.
        - Erstellen Sie KEINE Fragen, Optionen oder Erklärungen, die Diagramme, Abbildungen, Tabellen, Grafiken, Diagramme, Bilder, Illustrationen oder andere visuelle Hilfsmittel erwähnen, andeuten, darauf verweisen oder davon abhängen.
        - Jede Frage, ihre Optionen und Erklärung MUSS vollständig eigenständig, in sich geschlossen und verständlich sein, ohne jeglichen visuellen Kontext oder zusätzliche Ressourcen außer dem bereitgestellten Text.
        - Der "correct"-Wert MUSS eine Ganzzahl (0-3) sein, die den Index der richtigen Option im "options"-Array angibt, NICHT der Text der Antwort.
        """
    )

    prompt = (
        """
        Create multiple-choice test questions for the following material. Each question should have 4 options with only one correct answer.
        - Base questions and answers on key concepts in the text. If the text does not provide enough information to answer a question, invent a plausible, hypothetical scenario that aligns with the main topic and subtopics to provide a clear, informative answer.
        - Do NOT return answers or explanations like "Unknown" or "Not provided in the text." Instead, create a reasonable scenario based on the themes of the text.
        - Do NOT include any questions, options, or explanations that mention, imply, or rely on diagrams, figures, tables, graphs, charts, images, illustrations, or any other visual aids.
        - Options and explanations must be precise, informative, and fully self-contained, with NO references to visual elements or external context.
        - To ensure MAXIMUM VARIETY, invent entirely new, hypothetical scenarios or examples related to the main topic and subtopics, even if they are not explicitly mentioned in the text. These scenarios MUST be highly creative, with significantly different contexts, numbers, and phrasings compared to existing questions.
        - Analyze the existing questions (if provided) and ensure that no new questions repeat the exact wording, structure, numbers, or context of the existing questions. The new questions MUST be distinctly different in every aspect. For example:
          - If an existing question is "What is the effect of an increase in demand for mandatory health insurance in Switzerland?", do NOT create questions about Switzerland, health insurance demand increases, or similar structures. Instead, use a different country (e.g., Germany) and a different context (e.g., tax policy effects on healthcare).
          - If an existing question uses numbers like "4.5 million" or "30 EURO", avoid these numbers and use entirely different values (e.g., "200,000 units" or "15% tax").
          - If an existing question uses a phrase like "What is the effect of...", use a different structure (e.g., "How would a policy impact..." or "What are the consequences of...").
        - Format your response as a JSON array of objects with the keys "text", "options", "correct" (an integer 0-3), and "explanation".
        """
        if language != 'de' else
        """
        Erstellen Sie Multiple-Choice-Testfragen für das folgende Material. Jede Frage sollte 4 Antwortmöglichkeiten haben, wobei nur eine korrekt ist.
        - Stützen Sie Fragen und Antworten auf Schlüsselkonzepte im Text. Wenn der Text nicht genügend Informationen zur Beantwortung einer Frage bietet, erfinden Sie ein plausibles, hypothetisches Szenario, das mit dem Hauptthema und den Unterthemen übereinstimmt, um eine klare, informative Antwort zu geben.
        - Geben Sie KEINE Antworten oder Erklärungen wie "Unbekannt" oder "Nicht im Text angegeben" zurück. Erfinden Sie stattdessen ein vernünftiges Szenario basierend auf den Themen des Textes.
        - Fügen Sie KEINE Fragen, Optionen oder Erklärungen hinzu, die Diagramme, Abbildungen, Tabellen, Grafiken, Diagramme, Bilder, Illustrationen oder andere visuelle Hilfsmittel erwähnen, andeuten oder darauf angewiesen sind.
        - Die Optionen und Erklärungen müssen präzise, informativ und vollständig eigenständig sein, OHNE Verweise auf visuelle Elemente oder externen Kontext.
        - Um SICHERE Abwechslung zu gewährleisten, erfinden Sie völlig neue, hypothetische Szenarien oder Beispiele, die sich auf das Hauptthema und die Unterthemen beziehen, auch wenn sie nicht explizit im Text erwähnt sind. Diese Szenarien MÜSSEN hoch kreativ sein und sich deutlich in Kontext, Zahlen und Formulierungen von bestehenden Fragen unterscheiden.
        - Analysieren Sie die bestehenden Fragen (falls vorhanden) und stellen Sie sicher, dass keine neuen Fragen die genaue Wortwahl, Struktur, Zahlen oder Kontexte der vorhandenen Fragen wiederholen. Die neuen Fragen MÜSSEN in jedem Aspekt eindeutig unterschiedlich sein. Zum Beispiel:
          - Wenn eine vorhandene Frage lautet "What is the effect of an increase in demand for mandatory health insurance in Switzerland?", erstellen Sie KEINE Fragen über die Schweiz, Nachfrageerhöhungen bei Krankenversicherungen oder ähnliche Strukturen. Nutzen Sie stattdessen ein anderes Land (z. B. Deutschland) und einen anderen Kontext (z. B. Steuerpolitik-Effekte auf Gesundheitswesen).
          - Wenn eine vorhandene Frage Zahlen wie "4,5 Millionen" oder "30 EURO" verwendet, vermeiden Sie diese Zahlen und nutzen Sie völlig andere Werte (z. B. "200.000 Einheiten" oder "15% Steuer").
          - Wenn eine vorhandene Frage eine Formulierung wie "What is the effect of..." verwendet, nutzen Sie eine andere Struktur (z. B. "Wie würde eine Politik beeinflussen..." oder "Welche Folgen hat...").
        - Formatieren Sie Ihre Antwort als JSON-Array mit Objekten, die die Schlüssel "text", "options", "correct" (eine Ganzzahl 0-3) und "explanation" enthalten.
        """
    )

    if analysis:
        prompt += (
            f"\n\nMain topic: {analysis.get('main_topic', '')}\nSubtopics: {', '.join([subtopic['name'] if isinstance(subtopic, dict) and 'name' in subtopic else str(subtopic) for subtopic in analysis.get('subtopics', [])])}\n"
            if language != 'de' else
            f"\n\nHauptthema: {analysis.get('main_topic', '')}\nUnterthemen: {', '.join([subtopic['name'] if isinstance(subtopic, dict) and 'name' in subtopic else str(subtopic) for subtopic in analysis.get('subtopics', [])])}\n"
        )

    if existing_questions_list:
        prompt += (
            "\n\n### EXISTING QUESTIONS (DO NOT REUSE THESE EXACT QUESTIONS OR CREATE SIMILAR ONES) ###\n"
            if language != 'de' else
            "\n\n### BEREITS VORHANDENE FRAGEN (VERWENDEN SIE DIESE GENAUEN FRAGEN NICHT ODER ERSTELLEN SIE ÄHNLICHE) ###\n"
        )
        for i, q in enumerate(existing_questions_list):
            prompt += f"{i+1}. {q.get('text', '')}\n"
        prompt += (
            "\nCreate COMPLETELY NEW questions with entirely different structures, numbers, contexts, and topics, avoiding any similarity to the above existing questions.\n"
            if language != 'de' else
            "\nErstellen Sie KOMPLETT NEUE Fragen mit völlig anderen Strukturen, Zahlen, Kontexten und Themen, und vermeiden Sie jede Ähnlichkeit mit den oben genannten vorhandenen Fragen.\n"
        )

    num_questions = min(analysis.get('estimated_questions', 5), 8) if analysis else 5
    prompt += (
        f"\nCreate {num_questions} test questions for the following text:\n\n"
        if language != 'de' else
        f"\nErstellen Sie {num_questions} Testfragen für den folgenden Text:\n\n"
    )

    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"

    # Erhöhe die Temperatur für mehr Kreativität
    response = query_chatgpt(prompt + text, client, system_content, temperature=0.9)

    try:
        questions = json.loads(response)
        if not isinstance(questions, list):
            raise ValueError("Response is not a list")
        valid_questions = [q for q in questions if isinstance(q, dict) and 'text' in q and 'options' in q and 'correct' in q]
        return filter_visual_references(valid_questions, is_flashcard=False)
    except (json.JSONDecodeError, ValueError):
        pattern = r'(?:"text":\s*")(.*?)(?:")\s*,\s*"options":\s*\[(.*?)\]\s*,\s*"correct"\s*:\s*(\d+)'
        matches = re.findall(pattern, response, re.DOTALL)
        questions = []
        for text, options_str, correct in matches:
            options = re.findall(r'"([^"]*)"', options_str)
            if len(options) >= 2:
                questions.append({
                    "text": text,
                    "options": options,
                    "correct": int(correct),
                    "explanation": ""
                })
        return filter_visual_references(questions, is_flashcard=False) if questions else [{"text": "Could not generate test questions", "options": ["Try again"], "correct": 0, "explanation": ""}]

def unified_content_processing(text, client, file_names=None, language=None):
    """
    Verarbeitet den Text und generiert alle notwendigen Inhalte (Analyse, Flashcards, Fragen) in einem einzigen API-Aufruf.
    
    Args:
        text: Der zu verarbeitende Text
        client: Der OpenAI-Client
        file_names: Liste der Dateinamen (für intelligenten Fallback)
        language: Die Sprache des Textes (wird automatisch erkannt, wenn nicht angegeben)
    
    Returns:
        Ein Dictionary mit allen generierten Inhalten (Analyse, Flashcards, Fragen)
    """
    if language is None:
        language = detect_language(text)
        
    print(f"Verarbeitung von Text in Sprache: {language}")
    
    # Erhöhe das Zeichenlimit deutlich für GPT-4o
    # Verwendet etwa 80% der verfügbaren Tokens für den Eingabetext
    # 1 Token ≈ 4 Zeichen, GPT-4o hat 128K Token, reserviere einige für Antworten
    max_chars = 380000  # Etwa 95K Tokens für den Eingabetext
    
    if len(text) > max_chars:
        print(f"Text zu lang: {len(text)} Zeichen, kürze auf {max_chars} Zeichen")
        text = text[:max_chars] + "...[Text abgeschnitten]"
    else:
        print(f"Textgröße: {len(text)} Zeichen, ungefähr {len(text) // 4} Tokens")
    
    # Anzahl der Dokumente ermitteln für dynamische Anpassung der Anzahl von Flashcards und Fragen
    num_documents = len(file_names) if file_names else 1
    
    # Berechne die Mindestanzahl von Flashcards und Fragen basierend auf der Dokumentanzahl
    min_flashcards = max(8, num_documents * 5)    # Mindestens 5 pro Dokument, aber nicht weniger als 8 gesamt
    max_flashcards = min(30, min_flashcards * 2)  # Maximal 30, aber flexibel nach oben
    
    min_questions = max(5, num_documents * 3)     # Mindestens 3 pro Dokument, aber nicht weniger als 5 gesamt
    max_questions = min(20, min_questions * 2)    # Maximal 20, aber flexibel nach oben
    
    print(f"Dokumente: {num_documents}, Flashcards: {min_flashcards}-{max_flashcards}, Fragen: {min_questions}-{max_questions}")
    
    # System-Prompt für einen sehr spezialisierten Assistenten
    system_content = (
        """
        You are an AI academic assistant specialized in analyzing educational content and creating structured learning materials.
        Your task is to process academic text and generate a complete set of learning materials including:
        1. Hierarchical topic structure
        2. Flashcards for studying
        3. Multiple-choice questions for testing knowledge
        
        IMPORTANT: The input text might contain content from multiple documents combined together.
        Carefully analyze ALL of the provided content, including all documents, to create comprehensive learning materials.
        
        Follow these guidelines precisely:
        - Be comprehensive yet concise
        - Process and incorporate content from ALL provided documents
        - Focus on factual information across the entire corpus
        - Ensure all materials are self-contained and don't reference external resources
        - Create original, diverse content that explores topics from multiple angles
        - Do NOT include references to visual elements (figures, tables, etc.)
        - Ensure JSON formatting is valid and follows the specified structure exactly
        """
        if language != 'de' else
        """
        Sie sind ein KI-Akademiker-Assistent, der auf die Analyse von Bildungsinhalten und die Erstellung strukturierter Lernmaterialien spezialisiert ist.
        Ihre Aufgabe ist es, akademischen Text zu verarbeiten und einen vollständigen Satz von Lernmaterialien zu erstellen, darunter:
        1. Hierarchische Themenstruktur
        2. Karteikarten zum Lernen
        3. Multiple-Choice-Fragen zum Testen des Wissens
        
        WICHTIG: Der Eingabetext kann Inhalte aus mehreren zusammengefügten Dokumenten enthalten.
        Analysieren Sie sorgfältig ALLE bereitgestellten Inhalte, einschließlich aller Dokumente, um umfassende Lernmaterialien zu erstellen.
        
        Befolgen Sie diese Richtlinien genau:
        - Umfassend, aber prägnant
        - Verarbeiten und integrieren Sie Inhalte aus ALLEN bereitgestellten Dokumenten
        - Konzentration auf sachliche Informationen aus dem gesamten Textkorpus
        - Stellen Sie sicher, dass alle Materialien eigenständig sind und nicht auf externe Ressourcen verweisen
        - Erstellen Sie originale, vielfältige Inhalte, die Themen aus verschiedenen Blickwinkeln betrachten
        - Nehmen Sie KEINE Verweise auf visuelle Elemente auf (Abbildungen, Tabellen usw.)
        - Stellen Sie sicher, dass die JSON-Formatierung gültig ist und genau der angegebenen Struktur folgt
        """
    )
    
    # Der Hauptprompt, der alle notwendigen Teile in einem einzigen Aufruf anfordert
    prompt = (
        f"""
        Analyze the following text and create complete learning materials with these components:

        1. MAIN TOPIC: The core subject (one concise phrase, max 5 words)
        
        2. SUBTOPICS: 3-7 major areas within the main topic
           For each subtopic include 2-4 more specific child topics
        
        3. KEY TERMS: 5-10 important terms with concise definitions
        
        4. FLASHCARDS: {min_flashcards}-{max_flashcards} study flashcards (question/answer pairs)
           - Vary question types (definitions, applications, comparisons)
           - Cover different aspects of the material
           - Make questions and answers clear, concise, and standalone
           - IMPORTANT: Create flashcards that cover ALL content from ALL documents
           - Include at least 5 flashcards from each document
        
        5. TEST QUESTIONS: {min_questions}-{max_questions} multiple-choice questions
           - Each question must have exactly 4 options
           - Provide a clear explanation for the correct answer
           - Vary the difficulty and focus of questions
           - IMPORTANT: Create questions that cover ALL content from ALL documents
           - Include at least 3 questions from each document
        
        6. CONTENT TYPE: Identify the type (lecture, textbook, notes, etc.)

        IMPORTANT: I may provide multiple documents combined into a single text.
        You must analyze ALL the content, including sections from different documents.
        Create comprehensive learning materials that cover ALL of the topics present in the combined text.

        Respond with a SINGLE valid JSON object using this exact structure:
        {{
          "main_topic": "string",
          "subtopics": [
            {{ 
              "name": "string",
              "child_topics": ["string", "string", ...]
            }},
            ...
          ],
          "key_terms": [
            {{
              "term": "string",
              "definition": "string"
            }},
            ...
          ],
          "flashcards": [
            {{
              "question": "string",
              "answer": "string"
            }},
            ...
          ],
          "questions": [
            {{
              "text": "string",
              "options": ["string", "string", "string", "string"],
              "correct": number,
              "explanation": "string"
            }},
            ...
          ],
          "content_type": "string"
        }}

        Base your analysis on this text:
        """
        if language != 'de' else
        f"""
        Analysieren Sie den folgenden Text und erstellen Sie vollständige Lernmaterialien mit diesen Komponenten:

        1. HAUPTTHEMA: Das Kernthema (eine prägnante Phrase, max. 5 Wörter)
        
        2. UNTERTHEMEN: 3-7 wichtige Bereiche innerhalb des Hauptthemas
           Für jedes Unterthema fügen Sie 2-4 spezifischere Kinderthemen hinzu
        
        3. SCHLÜSSELBEGRIFFE: 5-10 wichtige Begriffe mit prägnanten Definitionen
        
        4. KARTEIKARTEN: {min_flashcards}-{max_flashcards} Lernkarteikarten (Frage/Antwort-Paare)
           - Variieren Sie die Fragetypen (Definitionen, Anwendungen, Vergleiche)
           - Decken Sie verschiedene Aspekte des Materials ab
           - Machen Sie Fragen und Antworten klar, prägnant und eigenständig
           - WICHTIG: Erstellen Sie Karteikarten, die ALLE Inhalte aus ALLEN Dokumenten abdecken
           - Erstellen Sie mindestens 5 Karteikarten für jedes Dokument
        
        5. TESTFRAGEN: {min_questions}-{max_questions} Multiple-Choice-Fragen
           - Jede Frage muss genau 4 Optionen haben
           - Geben Sie eine klare Erklärung für die richtige Antwort
           - Variieren Sie den Schwierigkeitsgrad und den Fokus der Fragen
           - WICHTIG: Erstellen Sie Fragen, die ALLE Inhalte aus ALLEN Dokumenten abdecken
           - Erstellen Sie mindestens 3 Fragen für jedes Dokument
        
        6. INHALTSTYP: Identifizieren Sie den Typ (Vorlesung, Lehrbuch, Notizen usw.)

        WICHTIG: Ich stelle möglicherweise mehrere Dokumente bereit, die zu einem einzigen Text kombiniert wurden.
        Sie müssen ALLE Inhalte analysieren, einschließlich Abschnitte aus verschiedenen Dokumenten.
        Erstellen Sie umfassende Lernmaterialien, die ALLE Themen im kombinierten Text abdecken.

        Antworten Sie mit EINEM gültigen JSON-Objekt mit dieser genauen Struktur:
        {{
          "main_topic": "string",
          "subtopics": [
            {{ 
              "name": "string",
              "child_topics": ["string", "string", ...]
            }},
            ...
          ],
          "key_terms": [
            {{
              "term": "string",
              "definition": "string"
            }},
            ...
          ],
          "flashcards": [
            {{
              "question": "string",
              "answer": "string"
            }},
            ...
          ],
          "questions": [
            {{
              "text": "string",
              "options": ["string", "string", "string", "string"],
              "correct": number,
              "explanation": "string"
            }},
            ...
          ],
          "content_type": "string"
        }}

        Basieren Sie Ihre Analyse auf diesem Text:
        """
    )
    
    # Probe einen Dateinamen für bessere thematische Hinweise extrahieren
    filename_hint = ""
    if file_names and len(file_names) > 0:
        filename_info = "\n\nDer Inhalt enthält folgende Dokumente:\n"
        for i, name in enumerate(file_names):
            filename_info += f"{i+1}. {name}\n"
        
        # Suche nach Dokumentmarkierungen im Text
        doc_markers = []
        for name in file_names:
            marker_pattern = f"=== DOKUMENT: {name} ==="
            if marker_pattern in text:
                doc_markers.append(name)
                
        if doc_markers:
            filename_info += "\nDie Dokumente sind im Text durch Markierungen wie '=== DOKUMENT: [Name] ===' getrennt. "
            filename_info += "Bitte analysieren Sie den GESAMTEN Inhalt aus ALLEN Dokumenten für Ihre Lernmaterialien."
            
        filename_hint = filename_info
    
    # Temperatur etwas erhöht für kreativere Inhalte
    complete_prompt = prompt + text + filename_hint
    
    # Versuche eine Antwort vom API zu bekommen - mit verbessertem Fehlerhandling
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"Sende Anfrage an OpenAI API (Versuch {attempt+1}/{max_retries})")
            
            response = client.chat.completions.create(
                model=current_app.config.get('OPENAI_MODEL', 'gpt-4o'),
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": complete_prompt}
                ],
                temperature=0.7,  # Guter Kompromiss zwischen Kreativität und Genauigkeit
                max_tokens=14000,  # Erhöht für umfangreichere Antworten
                timeout=180  # Längeres Timeout für komplexe Verarbeitung
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Versuche, das JSON zu parsen
            try:
                result = json.loads(response_text)
                
                # Validierung des Ergebnisses
                expected_keys = ['main_topic', 'subtopics', 'key_terms', 'flashcards', 'questions', 'content_type']
                missing_keys = [key for key in expected_keys if key not in result]
                
                if missing_keys:
                    print(f"Warnung: Fehlende Schlüssel im API-Ergebnis: {missing_keys}")
                    # Fehlende Schlüssel ergänzen
                    for key in missing_keys:
                        if key in ['subtopics', 'key_terms', 'flashcards', 'questions']:
                            result[key] = []
                        elif key == 'main_topic':
                            result[key] = "Unknown Topic"
                        elif key == 'content_type':
                            result[key] = "unknown"
                
                # Mindestprüfung auf Inhalte
                if (not result['flashcards'] or len(result['flashcards']) < 3 or 
                    not result['questions'] or len(result['questions']) < 2):
                    print("Warnung: Zu wenige Flashcards oder Fragen generiert, versuche erneut...")
                    continue
                
                return result
                
            except json.JSONDecodeError:
                print(f"Warnung: Antwort enthält kein gültiges JSON, versuche Fallback-Parsing (Versuch {attempt+1})")
                # Versuchen, die JSON-Struktur aus der Textantwort zu extrahieren
                try:
                    # Finde JSON-Block in der Antwort
                    json_match = re.search(r'```(?:json)?\s*(.*?)```', response_text, re.DOTALL) or re.search(r'({.*})', response_text, re.DOTALL)
                    
                    if json_match:
                        result = json.loads(json_match.group(1))
                        return result
                    else:
                        print("Kein JSON-Block in der Antwort gefunden")
                except:
                    print("Fallback-Parsing fehlgeschlagen")
                
                # Wenn wir hier sind, ist kein gültiges JSON gefunden worden
                if attempt < max_retries - 1:
                    # Versuche es noch einmal mit einem klareren Prompt
                    complete_prompt = prompt + "WICHTIG: Antworten Sie NUR mit einem gültigen JSON-Objekt!" + text + filename_hint
                else:
                    # Letzter Versuch gescheitert, verwende Fallback
                    break
                    
        except Exception as e:
            print(f"API-Fehler: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponentielles Backoff
                print(f"Warte {wait_time} Sekunden vor dem nächsten Versuch...")
                time.sleep(wait_time)
            else:
                print("Maximale Anzahl von Versuchen erreicht, verwende Fallback-Antwort")
                break
    
    # Wenn wir hier sind, verwenden wir den Fallback-Mechanismus
    return generate_smart_fallback(file_names, language)

def generate_smart_fallback(file_names, language='en'):
    """
    Generiert eine intelligente Fallback-Antwort basierend auf den Dateinamen.
    Wird verwendet, wenn die OpenAI API nicht verfügbar ist oder fehlschlägt.
    
    Args:
        file_names: Liste der Dateinamen
        language: Sprache der Antwort
    
    Returns:
        Ein Dictionary mit allen generierten Inhalten (Struktur wie bei unified_content_processing)
    """
    # Versuche, aus den Dateinamen Themenhints zu extrahieren
    topic_hints = {}
    if file_names and len(file_names) > 0:
        # Dateinamen in Kleinbuchstaben für besseren Vergleich
        combined_filenames = " ".join([name.lower() for name in file_names])
        
        # Verschiedene Themen-Kategorien erkennen
        if any(keyword in combined_filenames for keyword in ["nsa", "network", "security", "intrusion", "firewall", "crypto"]):
            topic_hints = {
                "main_topic": "Network Security Analysis",
                "subtopics": [
                    {"name": "Threat Detection", "child_topics": ["Intrusion Detection", "Anomaly Analysis", "Security Monitoring"]},
                    {"name": "Security Architecture", "child_topics": ["Firewalls", "Zero Trust", "Defense in Depth"]},
                    {"name": "Encryption Methods", "child_topics": ["Symmetric Encryption", "Asymmetric Encryption", "Key Management"]},
                    {"name": "Authentication Systems", "child_topics": ["Multi-factor Authentication", "Biometrics", "OAuth Protocols"]}
                ],
                "key_terms": [
                    {"term": "IDS", "definition": "Intrusion Detection System - Monitors network traffic for suspicious activity and policy violations."},
                    {"term": "Firewall", "definition": "Network security device that monitors and filters incoming/outgoing traffic based on security policies."},
                    {"term": "Encryption", "definition": "Process of encoding information to prevent unauthorized access."},
                    {"term": "Zero Trust", "definition": "Security model that requires strict identity verification for every person and device."},
                    {"term": "VPN", "definition": "Virtual Private Network - Creates a secure, encrypted connection over a less secure network."}
                ],
                "content_type": "lecture"
            }
        elif any(keyword in combined_filenames for keyword in ["program", "code", "algorithm", "data", "struct"]):
            topic_hints = {
                "main_topic": "Programming & Algorithms",
                "subtopics": [
                    {"name": "Data Structures", "child_topics": ["Arrays", "Linked Lists", "Trees", "Hash Tables"]},
                    {"name": "Algorithm Complexity", "child_topics": ["Time Complexity", "Space Complexity", "Big O Notation"]},
                    {"name": "Software Design", "child_topics": ["Object-Oriented Programming", "Functional Programming", "Design Patterns"]},
                    {"name": "Problem Solving", "child_topics": ["Divide and Conquer", "Dynamic Programming", "Greedy Algorithms"]}
                ],
                "key_terms": [
                    {"term": "Algorithm", "definition": "Step-by-step procedure for calculations, data processing, or automated reasoning."},
                    {"term": "Data Structure", "definition": "Specific way of organizing data to use it efficiently."},
                    {"term": "Recursion", "definition": "Method where solution depends on solutions to smaller instances of the same problem."},
                    {"term": "Complexity", "definition": "Measure of resources (time, space) required by an algorithm to run."},
                    {"term": "Object-Oriented", "definition": "Programming paradigm based on objects containing data and methods."}
                ],
                "content_type": "lecture"
            }
        elif any(keyword in combined_filenames for keyword in ["math", "calc", "algebra", "statistics", "probability"]):
            topic_hints = {
                "main_topic": "Mathematical Concepts",
                "subtopics": [
                    {"name": "Calculus", "child_topics": ["Derivatives", "Integrals", "Differential Equations", "Limits"]},
                    {"name": "Linear Algebra", "child_topics": ["Vectors", "Matrices", "Linear Transformations", "Eigenvalues"]},
                    {"name": "Probability Theory", "child_topics": ["Random Variables", "Distributions", "Expected Values", "Stochastic Processes"]},
                    {"name": "Discrete Mathematics", "child_topics": ["Graph Theory", "Combinatorics", "Number Theory", "Logic"]}
                ],
                "key_terms": [
                    {"term": "Derivative", "definition": "Rate at which a function changes at a particular point."},
                    {"term": "Vector", "definition": "Quantity having both magnitude and direction."},
                    {"term": "Probability", "definition": "Measure of the likelihood that an event will occur."},
                    {"term": "Matrix", "definition": "Rectangular array of numbers arranged in rows and columns."},
                    {"term": "Function", "definition": "Relation that associates each element of a set with exactly one element of another set."}
                ],
                "content_type": "lecture"
            }
        else:
            # Generisches akademisches Thema als Fallback
            topic_hints = {
                "main_topic": "Academic Study Methods",
                "subtopics": [
                    {"name": "Effective Learning", "child_topics": ["Spaced Repetition", "Active Recall", "Mind Mapping", "Feynman Technique"]},
                    {"name": "Research Skills", "child_topics": ["Literature Review", "Data Collection", "Critical Analysis", "Academic Writing"]},
                    {"name": "Time Management", "child_topics": ["Pomodoro Technique", "Priority Matrix", "Time Blocking", "Goal Setting"]},
                    {"name": "Critical Thinking", "child_topics": ["Logical Reasoning", "Cognitive Biases", "Argumentation", "Problem Solving"]}
                ],
                "key_terms": [
                    {"term": "Metacognition", "definition": "Awareness and understanding of one's own thought processes."},
                    {"term": "Active Recall", "definition": "Learning technique that involves actively stimulating memory during the learning process."},
                    {"term": "Spaced Repetition", "definition": "Technique where review of material is spread out over time to improve long-term retention."},
                    {"term": "Critical Analysis", "definition": "Detailed examination and evaluation of something, especially information."},
                    {"term": "Cognitive Bias", "definition": "Systematic pattern of deviation from norm or rationality in judgment."}
                ],
                "content_type": "study guide"
            }
    else:
        # Ohne Dateinamen - allgemeines akademisches Lernen
        topic_hints = {
            "main_topic": "Academic Study Skills",
            "subtopics": [
                {"name": "Note-Taking Methods", "child_topics": ["Cornell Method", "Mind Mapping", "Outline Method", "Charting Method"]},
                {"name": "Exam Preparation", "child_topics": ["Practice Tests", "Group Study", "Memory Techniques", "Stress Management"]},
                {"name": "Research Methods", "child_topics": ["Source Evaluation", "Data Analysis", "Citation Practices", "Research Ethics"]},
                {"name": "Academic Writing", "child_topics": ["Essay Structure", "Critical Writing", "Peer Review", "Editing Techniques"]}
            ],
            "key_terms": [
                {"term": "Academic Integrity", "definition": "Adherence to ethical standards in academic work, including honesty and respect for others' intellectual property."},
                {"term": "Critical Thinking", "definition": "The objective analysis and evaluation of an issue to form a judgment."},
                {"term": "Literature Review", "definition": "A survey of scholarly materials relevant to a specific research question."},
                {"term": "Peer Review", "definition": "Evaluation of work by one or more people with similar competencies as the producers of the work."},
                {"term": "Citation", "definition": "A reference to a published or unpublished source used in academic writing."}
            ],
            "content_type": "educational resources"
        }
    
    # Generiere Flashcards basierend auf den Themenhinweisen
    flashcards = []
    for subtopic in topic_hints["subtopics"]:
        # Hauptfrage zum Unterthema
        flashcards.append({
            "question": f"What are the key components of {subtopic['name']}?",
            "answer": f"The key components include {', '.join(subtopic['child_topics'])}."
        })
        
        # Weitere Fragen zu den Unterunterthemen
        for child in subtopic["child_topics"][:2]:  # Beschränke auf 2 pro Unterthema
            flashcards.append({
                "question": f"Explain the concept of {child} in the context of {subtopic['name']}.",
                "answer": f"{child} is a crucial element within {subtopic['name']} that helps students effectively organize and process information."
            })
    
    # Generiere ein paar Fragen zu Schlüsselbegriffen
    for term in topic_hints["key_terms"][:3]:
        flashcards.append({
            "question": f"Define {term['term']} and explain its importance.",
            "answer": f"{term['term']}: {term['definition']} It is important because it forms a fundamental concept in this field."
        })
    
    # Begrenze die Anzahl der Flashcards
    flashcards = flashcards[:12]
    
    # Generiere Multiple-Choice-Fragen
    questions = []
    for subtopic in topic_hints["subtopics"][:3]:
        questions.append({
            "text": f"Which of the following is NOT part of {subtopic['name']}?",
            "options": subtopic["child_topics"][:3] + ["All of the above are part of it"],
            "correct": 3,
            "explanation": f"All the listed elements are core components of {subtopic['name']}."
        })
    
    # Fragen zu Schlüsselbegriffen
    for term in topic_hints["key_terms"][:2]:
        questions.append({
            "text": f"What is the best definition of {term['term']}?",
            "options": [
                term["definition"],
                "A complex mathematical formula used in data analysis",
                "A software tool for organizing research papers",
                "A collaborative learning technique used in group studies"
            ],
            "correct": 0,
            "explanation": f"The correct definition of {term['term']} is: {term['definition']}"
        })
    
    # Vollständiges Ergebnis zusammenstellen
    return {
        "main_topic": topic_hints["main_topic"],
        "subtopics": topic_hints["subtopics"],
        "key_terms": topic_hints["key_terms"],
        "flashcards": flashcards,
        "questions": questions,
        "content_type": topic_hints["content_type"]
    }

def generate_additional_flashcards(text, client, analysis, existing_flashcards, num_to_generate=5, language='en'):
    """
    Generiert zusätzliche, einzigartige Flashcards, die sich von den bestehenden unterscheiden.
    
    Args:
        text: Der Textinhalt für die Generierung
        client: Der OpenAI-Client
        analysis: Das Analyseergebnis mit Hauptthema und Unterthemen
        existing_flashcards: Die bereits vorhandenen Flashcards
        num_to_generate: Anzahl der zu generierenden neuen Flashcards
        language: Die Sprache der Flashcards
        
    Returns:
        Liste mit neuen, einzigartigen Flashcards
    """
    # Nutze die vorhandene Funktion, aber mit spezifischen Anweisungen
    system_content = (
        """
        You are an expert in creating ADDITIONAL educational flashcards. Your task is to generate flashcards that are COMPLETELY DIFFERENT from the existing ones.
        
        CRITICAL INSTRUCTIONS:
        - Study the existing flashcards carefully to understand what's already covered
        - Create NEW flashcards that explore DIFFERENT aspects, angles, and applications
        - Do NOT duplicate or rephrase existing flashcards
        - Ensure variety in question types, complexity levels, and topic coverage
        - Focus on areas, concepts, and applications not yet addressed
        - Make each new flashcard substantially different from all existing ones
        - ALWAYS use English for all flashcards
        """
        if language != 'de' else
        """
        Sie sind ein Experte für die Erstellung ZUSÄTZLICHER Lernkarteikarten. Ihre Aufgabe ist es, Karteikarten zu erstellen, die sich VOLLSTÄNDIG von den vorhandenen unterscheiden.
        
        KRITISCHE ANWEISUNGEN:
        - Studieren Sie die vorhandenen Karteikarten sorgfältig, um zu verstehen, was bereits abgedeckt ist
        - Erstellen Sie NEUE Karteikarten, die ANDERE Aspekte, Blickwinkel und Anwendungen erkunden
        - Duplizieren oder umformulieren Sie KEINE vorhandenen Karteikarten
        - Achten Sie auf Vielfalt bei Fragetypen, Komplexitätsstufen und Themenabdeckung
        - Konzentrieren Sie sich auf Bereiche, Konzepte und Anwendungen, die noch nicht behandelt wurden
        - Machen Sie jede neue Karteikarte wesentlich anders als alle vorhandenen
        - Verwenden Sie IMMER Deutsch für alle Karteikarten
        """
    )
    
    prompt = (
        f"""
        I need {num_to_generate} ADDITIONAL, UNIQUE flashcards that are COMPLETELY DIFFERENT from the existing ones.
        
        Main Topic: {analysis.get('main_topic', '')}
        Subtopics: {', '.join([subtopic['name'] if isinstance(subtopic, dict) and 'name' in subtopic else str(subtopic) for subtopic in analysis.get('subtopics', [])])}
        
        EXISTING FLASHCARDS (DO NOT DUPLICATE OR REPHRASE THESE):
        """
        if language != 'de' else
        f"""
        Ich benötige {num_to_generate} ZUSÄTZLICHE, EINZIGARTIGE Karteikarten, die sich VÖLLIG von den vorhandenen unterscheiden.
        
        Hauptthema: {analysis.get('main_topic', '')}
        Unterthemen: {', '.join([subtopic['name'] if isinstance(subtopic, dict) and 'name' in subtopic else str(subtopic) for subtopic in analysis.get('subtopics', [])])}
        
        VORHANDENE KARTEIKARTEN (DIESE NICHT DUPLIZIEREN ODER UMFORMULIEREN):
        """
    )
    
    # Füge die vorhandenen Flashcards zum Prompt hinzu, damit sie nicht dupliziert werden
    for i, fc in enumerate(existing_flashcards[:10]):  # Begrenze auf 10 vorhandene Karten, um den Prompt nicht zu lang zu machen
        if language != 'de':
            prompt += f"\n{i+1}. Q: {fc.get('question', '')} A: {fc.get('answer', '')}"
        else:
            prompt += f"\n{i+1}. F: {fc.get('question', '')} A: {fc.get('answer', '')}"
    
    # Füge Beispiele für die Art von Flashcards hinzu, die wir suchen
    if language != 'de':
        prompt += """
        
        FORMAT REQUIREMENTS:
        - Each flashcard should be in the format "Q: [question] A: [answer]"
        - Questions should be clear, specific, and thought-provoking
        - Answers should be comprehensive but concise, about 2-3 sentences
        - Make the flashcards challenging but still directly relevant to the content
        
        RETURN ONLY THE FLASHCARDS IN THIS JSON FORMAT:
        [
          {"question": "Your question here", "answer": "Your answer here"},
          {"question": "Your question here", "answer": "Your answer here"}
        ]
        """
    else:
        prompt += """
        
        FORMATANFORDERUNGEN:
        - Jede Karteikarte sollte im Format "F: [Frage] A: [Antwort]" sein
        - Fragen sollten klar, spezifisch und zum Nachdenken anregend sein
        - Antworten sollten umfassend aber prägnant sein, etwa 2-3 Sätze
        - Machen Sie die Karteikarten herausfordernd, aber dennoch direkt relevant für den Inhalt
        
        GEBEN SIE NUR DIE KARTEIKARTEN IN DIESEM JSON-FORMAT ZURÜCK:
        [
          {"question": "Ihre Frage hier", "answer": "Ihre Antwort hier"},
          {"question": "Ihre Frage hier", "answer": "Ihre Antwort hier"}
        ]
        """
    
    try:
        # Generiere die neuen Flashcards
        flashcards_response = query_chatgpt(prompt, client, system_content=system_content, temperature=0.8)
        print(f"Flashcards response: {flashcards_response[:200]}...")  # DEBUG: Zeige Anfang der Antwort
        
        # Extrahiere den JSON-Teil aus der Antwort
        match = re.search(r'\[.*\]', flashcards_response, re.DOTALL)
        if match:
            flashcards_json = match.group(0)
            new_flashcards = json.loads(flashcards_json)
            
            # Verifiziere, dass die Antwort im richtigen Format ist
            if isinstance(new_flashcards, list) and all(isinstance(f, dict) and 'question' in f and 'answer' in f for f in new_flashcards):
                return new_flashcards
        
        # Wenn das Format nicht passt oder kein JSON gefunden wurde, versuche erneut zu parsen
        try:
            # Versuche die gesamte Antwort als JSON zu interpretieren
            new_flashcards = json.loads(flashcards_response)
            if isinstance(new_flashcards, list) and all(isinstance(f, dict) and 'question' in f and 'answer' in f for f in new_flashcards):
                return new_flashcards
        except json.JSONDecodeError:
            # Wenn das nicht funktioniert, extrahiere mit einem anderen Regex
            flashcards_list = []
            # Suche nach {"question": ... "answer": ...} Mustern
            pattern = r'{"question":\s*"([^"]+)",\s*"answer":\s*"([^"]+)"}'
            matches = re.findall(pattern, flashcards_response)
            for q, a in matches:
                flashcards_list.append({"question": q, "answer": a})
            
            if flashcards_list:
                return flashcards_list
    except Exception as e:
        print(f"Error generating flashcards: {str(e)}")
    
    # Fallback: Erstelle einfache generische Flashcards, wenn nichts anderes funktioniert
    if language != 'de':
        return [
            {
                "question": f"What are the key components of {analysis.get('main_topic', 'this topic')}?",
                "answer": "The key components include understanding the fundamental principles, practical applications, and theoretical frameworks within this field."
            },
            {
                "question": f"How would you explain {analysis.get('main_topic', 'this concept')} to a beginner?",
                "answer": f"{analysis.get('main_topic', 'This concept')} can be explained as a systematic approach to organizing knowledge and solving problems within a specific domain."
            }
        ]
    else:
        return [
            {
                "question": f"Was sind die Hauptkomponenten von {analysis.get('main_topic', 'diesem Thema')}?",
                "answer": "Die Hauptkomponenten umfassen das Verständnis der grundlegenden Prinzipien, praktischen Anwendungen und theoretischen Rahmenbedingungen in diesem Bereich."
            },
            {
                "question": f"Wie würden Sie {analysis.get('main_topic', 'dieses Konzept')} einem Anfänger erklären?",
                "answer": f"{analysis.get('main_topic', 'Dieses Konzept')} kann als systematischer Ansatz zur Organisation von Wissen und zur Lösung von Problemen in einem bestimmten Bereich erklärt werden."
            }
        ]

def generate_additional_questions(text, client, analysis, existing_questions, num_to_generate=3, language='en'):
    """
    Generiert zusätzliche, einzigartige Testfragen, die sich von den bestehenden unterscheiden.
    
    Args:
        text: Der Textinhalt für die Generierung
        client: Der OpenAI-Client
        analysis: Das Analyseergebnis mit Hauptthema und Unterthemen
        existing_questions: Die bereits vorhandenen Testfragen
        num_to_generate: Anzahl der zu generierenden neuen Testfragen
        language: Die Sprache der Testfragen
        
    Returns:
        Liste mit neuen, einzigartigen Testfragen
    """
    # Nutze die vorhandene Funktion, aber mit spezifischen Anweisungen
    system_content = (
        """
        You are an expert in creating ADDITIONAL educational multiple-choice test questions. Your task is to generate questions that are COMPLETELY DIFFERENT from the existing ones.
        
        CRITICAL INSTRUCTIONS:
        - Study the existing questions carefully to understand what's already covered
        - Create NEW questions that explore DIFFERENT aspects, angles, and applications
        - Do NOT duplicate or rephrase existing questions
        - Ensure variety in question types, complexity levels, and topic coverage
        - Focus on areas, concepts, and applications not yet addressed
        - Make each new question substantially different from all existing ones
        - ALWAYS use English for all questions
        """
        if language != 'de' else
        """
        Sie sind ein Experte für die Erstellung ZUSÄTZLICHER Multiple-Choice-Testfragen. Ihre Aufgabe ist es, Fragen zu erstellen, die sich VOLLSTÄNDIG von den vorhandenen unterscheiden.
        
        KRITISCHE ANWEISUNGEN:
        - Studieren Sie die vorhandenen Fragen sorgfältig, um zu verstehen, was bereits abgedeckt ist
        - Erstellen Sie NEUE Fragen, die ANDERE Aspekte, Blickwinkel und Anwendungen erkunden
        - Duplizieren oder umformulieren Sie KEINE vorhandenen Fragen
        - Achten Sie auf Vielfalt bei Fragetypen, Komplexitätsstufen und Themenabdeckung
        - Konzentrieren Sie sich auf Bereiche, Konzepte und Anwendungen, die noch nicht behandelt wurden
        - Machen Sie jede neue Frage wesentlich anders als alle vorhandenen
        - Verwenden Sie IMMER Deutsch für alle Fragen
        """
    )
    
    prompt = (
        f"""
        I need {num_to_generate} ADDITIONAL, UNIQUE multiple-choice test questions that are COMPLETELY DIFFERENT from the existing ones.
        
        Main Topic: {analysis.get('main_topic', '')}
        Subtopics: {', '.join([subtopic['name'] if isinstance(subtopic, dict) and 'name' in subtopic else str(subtopic) for subtopic in analysis.get('subtopics', [])])}
        
        EXISTING QUESTIONS (DO NOT DUPLICATE OR REPHRASE THESE):
        """
        if language != 'de' else
        f"""
        Ich benötige {num_to_generate} ZUSÄTZLICHE, EINZIGARTIGE Multiple-Choice-Testfragen, die sich VÖLLIG von den vorhandenen unterscheiden.
        
        Hauptthema: {analysis.get('main_topic', '')}
        Unterthemen: {', '.join([subtopic['name'] if isinstance(subtopic, dict) and 'name' in subtopic else str(subtopic) for subtopic in analysis.get('subtopics', [])])}
        
        VORHANDENE FRAGEN (DIESE NICHT DUPLIZIEREN ODER UMFORMULIEREN):
        """
    )
    
    # Füge die vorhandenen Fragen zum Prompt hinzu, damit sie nicht dupliziert werden
    for i, q in enumerate(existing_questions[:5]):  # Begrenze auf 5 vorhandene Fragen, um den Prompt nicht zu lang zu machen
        prompt += f"\n{i+1}. Q: {q.get('text', '')}"
        if 'options' in q:
            prompt += f"\nOptions: {q.get('options', [])}"
        if 'correct' in q:
            prompt += f"\nCorrect Answer: {q.get('correct', 0)}"
        if 'explanation' in q:
            prompt += f"\nExplanation: {q.get('explanation', '')}"
    
    # Füge Beispiele für die Art von Testfragen hinzu, die wir suchen
    if language != 'de':
        prompt += """
        
        FORMAT REQUIREMENTS:
        - Each question should have a clear, specific prompt
        - Provide exactly 4 options for each question
        - Exactly one option should be correct
        - Include a brief explanation of why the correct answer is right
        - Vary question types (e.g., "which is NOT...", "what is the best...", etc.)
        
        RETURN ONLY THE QUESTIONS IN THIS JSON FORMAT:
        [
          {
            "text": "Your question here",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 0,  // Index of correct option (0-3)
            "explanation": "Brief explanation of the correct answer"
          }
        ]
        """
    else:
        prompt += """
        
        FORMATANFORDERUNGEN:
        - Jede Frage sollte eine klare, spezifische Formulierung haben
        - Geben Sie genau 4 Optionen für jede Frage an
        - Genau eine Option sollte korrekt sein
        - Fügen Sie eine kurze Erläuterung bei, warum die richtige Antwort korrekt ist
        - Variieren Sie die Fragetypen (z.B. "welches ist NICHT...", "was ist am besten...", usw.)
        
        GEBEN SIE NUR DIE FRAGEN IN DIESEM JSON-FORMAT ZURÜCK:
        [
          {
            "text": "Ihre Frage hier",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 0,  // Index der richtigen Option (0-3)
            "explanation": "Kurze Erklärung der richtigen Antwort"
          }
        ]
        """
    
    try:
        # Generiere die neuen Testfragen
        questions_response = query_chatgpt(prompt, client, system_content=system_content, temperature=0.8)
        print(f"Questions response: {questions_response[:200]}...")  # DEBUG: Zeige Anfang der Antwort
        
        # Extrahiere den JSON-Teil aus der Antwort
        match = re.search(r'\[.*\]', questions_response, re.DOTALL)
        if match:
            questions_json = match.group(0)
            new_questions = json.loads(questions_json)
            
            # Verifiziere, dass die Antwort im richtigen Format ist
            if isinstance(new_questions, list) and all(isinstance(q, dict) and 'text' in q and 'options' in q and 'correct' in q for q in new_questions):
                return new_questions
        
        # Wenn das Format nicht passt oder kein JSON gefunden wurde, versuche erneut zu parsen
        try:
            # Versuche die gesamte Antwort als JSON zu interpretieren
            new_questions = json.loads(questions_response)
            if isinstance(new_questions, list) and all(isinstance(q, dict) and 'text' in q and 'options' in q and 'correct' in q for q in new_questions):
                return new_questions
        except json.JSONDecodeError:
            # Wenn das nicht funktioniert, extrahiere mit einem anderen Regex
            questions_list = []
            # Suche nach {"text": ... "options": ... "correct": ... "explanation": ...} Mustern
            pattern = r'{"text":\s*"([^"]+)",\s*"options":\s*(\[[^\]]+\]),\s*"correct":\s*(\d+),\s*"explanation":\s*"([^"]+)"}'
            matches = re.findall(pattern, questions_response)
            for text, options_str, correct, explanation in matches:
                try:
                    options = json.loads(options_str)
                    questions_list.append({
                        "text": text,
                        "options": options,
                        "correct": int(correct),
                        "explanation": explanation
                    })
                except:
                    continue
            
            if questions_list:
                return questions_list
    except Exception as e:
        print(f"Error generating questions: {str(e)}")
    
    # Fallback: Erstelle einfache generische Testfragen, wenn nichts anderes funktioniert
    if language != 'de':
        return [
            {
                "text": f"Which of the following best describes {analysis.get('main_topic', 'this topic')}?",
                "options": [
                    "A systematic approach to problem-solving in the field",
                    "A random collection of unrelated concepts",
                    "A purely theoretical framework with no practical applications",
                    "A deprecated methodology no longer used in modern practice"
                ],
                "correct": 0,
                "explanation": f"{analysis.get('main_topic', 'This topic')} is primarily characterized by its systematic approach to problem-solving."
            },
            {
                "text": f"Which of the following is NOT a key component of {analysis.get('main_topic', 'this field')}?",
                "options": [
                    "Theoretical foundations",
                    "Practical applications",
                    "Systematic methodology",
                    "Arbitrary decision-making"
                ],
                "correct": 3,
                "explanation": "Arbitrary decision-making contradicts the systematic nature of this field, which relies on structured approaches."
            }
        ]
    else:
        return [
            {
                "text": f"Welche der folgenden Beschreibungen trifft am besten auf {analysis.get('main_topic', 'dieses Thema')} zu?",
                "options": [
                    "Ein systematischer Ansatz zur Problemlösung in diesem Bereich",
                    "Eine zufällige Sammlung unzusammenhängender Konzepte",
                    "Ein rein theoretisches Rahmenwerk ohne praktische Anwendungen",
                    "Eine veraltete Methodik, die in der modernen Praxis nicht mehr verwendet wird"
                ],
                "correct": 0,
                "explanation": f"{analysis.get('main_topic', 'Dieses Thema')} zeichnet sich hauptsächlich durch seinen systematischen Ansatz zur Problemlösung aus."
            },
            {
                "text": f"Welche der folgenden Komponenten ist KEINE Schlüsselkomponente von {analysis.get('main_topic', 'diesem Bereich')}?",
                "options": [
                    "Theoretische Grundlagen",
                    "Praktische Anwendungen",
                    "Systematische Methodik",
                    "Willkürliche Entscheidungsfindung"
                ],
                "correct": 3,
                "explanation": "Willkürliche Entscheidungsfindung widerspricht der systematischen Natur dieses Bereichs, der auf strukturierten Ansätzen basiert."
            }
        ]

def generate_concept_map_suggestions(text, client, main_topic, parent_subtopics, language='en'):
    """
    Generiert KI-Vorschläge für Kinder-Subtopics einer Concept-Map.
    
    Args:
        text: Der Textinhalt für die Generierung
        client: Der OpenAI-Client
        main_topic: Das Hauptthema der Concept-Map
        parent_subtopics: Die übergeordneten Subtopics
        language: Die Sprache der Vorschläge
        
    Returns:
        Dictionary mit den übergeordneten Subtopics als Schlüssel und Listen von vorgeschlagenen
        Kinder-Subtopics als Werte, zusammen mit Vorschlägen für Verbindungs-Labels
    """
    system_content = (
        """
        You are an expert in educational knowledge mapping and concept organization. Your task is to analyze text and generate meaningful child subtopics for a concept map.
        
        CRITICAL INSTRUCTIONS:
        - Provide child subtopics that are specific, meaningful, and directly related to their parent topics
        - Ensure each child subtopic represents a distinct and important aspect of its parent topic
        - Use concise, clear terminology that accurately represents the concept
        - Aim for consistency in the level of abstraction across child topics
        - Each child subtopic should be 1-4 words, very concise and focused
        - Provide 2-4 child subtopics for each parent topic
        - For each child subtopic, include a meaningful connection label that explains the relationship between the parent and child topic
        - The connection label should be a short phrase (3-10 words) that clearly describes why these topics are connected
        - ALWAYS use English for all topics and labels
        """
        if language != 'de' else
        """
        Sie sind ein Experte für pädagogische Wissenskartierung und Konzeptorganisation. Ihre Aufgabe ist es, Texte zu analysieren und aussagekräftige Kinder-Unterthemen für eine Concept-Map zu generieren.
        
        KRITISCHE ANWEISUNGEN:
        - Stellen Sie Kinder-Unterthemen bereit, die spezifisch, aussagekräftig und direkt mit ihren übergeordneten Themen verbunden sind
        - Stellen Sie sicher, dass jedes Kinder-Unterthema einen eigenständigen und wichtigen Aspekt seines übergeordneten Themas darstellt
        - Verwenden Sie prägnante, klare Terminologie, die das Konzept genau wiedergibt
        - Streben Sie nach Konsistenz im Abstraktionsgrad über alle Kinderthemen hinweg
        - Jedes Kinder-Unterthema sollte 1-4 Wörter umfassen, sehr prägnant und fokussiert sein
        - Geben Sie 2-4 Kinder-Unterthemen für jedes übergeordnete Thema an
        - Fügen Sie für jedes Kinder-Unterthema ein aussagekräftiges Beziehungslabel an, das die Beziehung zwischen dem Eltern- und dem Kindthema erklärt
        - Das Verbindungslabel sollte eine kurze Phrase (3-10 Wörter) sein, die klar beschreibt, warum diese Themen verbunden sind
        - Verwenden Sie IMMER Deutsch für alle Themen und Labels
        """
    )
    
    prompt = (
        f"""
        Generate child subtopics for a concept map based on the following structure:
        
        Main Topic: {main_topic}
        
        Parent Subtopics:
        {", ".join(parent_subtopics)}
        
        For each parent subtopic, please suggest 2-4 specific, meaningful child subtopics that represent important aspects of the parent topic. Each child subtopic should be concise (1-4 words).
        
        IMPORTANT: For each child subtopic, also provide a meaningful relationship label that explains why the child topic is connected to its parent topic.
        
        Format your response as a JSON object where each key is a parent subtopic and its value is an array of objects with "topic" and "relationship" properties.
        
        Example format:
        {{
          "Parent Subtopic 1": [
            {{ "topic": "Child Topic 1", "relationship": "is a fundamental component of" }},
            {{ "topic": "Child Topic 2", "relationship": "provides methods for" }},
            {{ "topic": "Child Topic 3", "relationship": "illustrates the application of" }}
          ],
          "Parent Subtopic 2": [
            {{ "topic": "Child Topic 1", "relationship": "emerged historically from" }},
            {{ "topic": "Child Topic 2", "relationship": "represents a specialized case of" }}
          ]
        }}
        """
        if language != 'de' else
        f"""
        Generieren Sie Kinder-Unterthemen für eine Concept-Map basierend auf der folgenden Struktur:
        
        Hauptthema: {main_topic}
        
        Übergeordnete Unterthemen:
        {", ".join(parent_subtopics)}
        
        Schlagen Sie für jedes übergeordnete Unterthema 2-4 spezifische, aussagekräftige Kinder-Unterthemen vor, die wichtige Aspekte des übergeordneten Themas darstellen. Jedes Kinder-Unterthema sollte prägnant sein (1-4 Wörter).
        
        WICHTIG: Geben Sie für jedes Kinder-Unterthema auch ein aussagekräftiges Beziehungslabel an, das erklärt, warum das Kinderthema mit seinem Elternthema verbunden ist.
        
        Formatieren Sie Ihre Antwort als JSON-Objekt, bei dem jeder Schlüssel ein übergeordnetes Unterthema ist und sein Wert ein Array von Objekten mit den Eigenschaften "topic" und "relationship" ist.
        
        Beispielformat:
        {{
          "Übergeordnetes Unterthema 1": [
            {{ "topic": "Kinderthema 1", "relationship": "ist eine grundlegende Komponente von" }},
            {{ "topic": "Kinderthema 2", "relationship": "bietet Methoden für" }},
            {{ "topic": "Kinderthema 3", "relationship": "veranschaulicht die Anwendung von" }}
          ],
          "Übergeordnetes Unterthema 2": [
            {{ "topic": "Kinderthema 1", "relationship": "entwickelte sich historisch aus" }},
            {{ "topic": "Kinderthema 2", "relationship": "repräsentiert einen spezialisierten Fall von" }}
          ]
        }}
        """
    )
    
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "...[text truncated]"
    
    response = query_chatgpt(prompt + "\n\n" + text, client, system_content, temperature=0.7)
    
    try:
        # Versuche, die Antwort als JSON zu parsen
        import json
        suggestions = json.loads(response)
        if not isinstance(suggestions, dict):
            raise ValueError("Response is not a dictionary")
        
        # Verarbeite die Antwort ins erwartete Format
        result = {}
        for parent, children in suggestions.items():
            # Überprüfe, ob die Kinder im neuen Format (mit topic und relationship) oder im alten Format sind
            if isinstance(children, list) and all(isinstance(child, dict) and "topic" in child for child in children):
                # Neues Format mit topic und relationship
                result[parent] = [child["topic"] for child in children]
                # Speichere die Beziehung im relationship_labels Dictionary
                relationship_labels = {}
                for child in children:
                    relationship_labels[child["topic"]] = child.get("relationship", f"ist ein Aspekt von {parent}")
                result[f"{parent}_relationships"] = relationship_labels
            else:
                # Altes Format - nur Liste von Themen
                result[parent] = children
                # Erstelle generische Beziehungslabels
                relationship_labels = {}
                for child in children:
                    relationship_labels[child] = f"ist ein Aspekt von {parent}"
                result[f"{parent}_relationships"] = relationship_labels
        
        # Validiere, dass alle übergeordneten Subtopics enthalten sind
        for parent in parent_subtopics:
            if parent not in result:
                if language == 'de':
                    children = ["Beispielkind 1", "Beispielkind 2"]
                    result[parent] = children
                    # Füge generische Beziehungslabels hinzu
                    relationship_labels = {}
                    for child in children:
                        relationship_labels[child] = f"ist ein Aspekt von {parent}"
                    result[f"{parent}_relationships"] = relationship_labels
                else:
                    children = ["Example Child 1", "Example Child 2"]
                    result[parent] = children
                    # Füge generische Beziehungslabels hinzu
                    relationship_labels = {}
                    for child in children:
                        relationship_labels[child] = f"is an aspect of {parent}"
                    result[f"{parent}_relationships"] = relationship_labels
        
        return result
    except (json.JSONDecodeError, ValueError) as e:
        import logging
        logging.error(f"Error parsing JSON response: {str(e)}")
        logging.error(f"Raw response: {response}")
        # Fallback: Erstelle ein einfaches Wörterbuch mit generischen Kindern und Beziehungen
        fallback_suggestions = {}
        for parent in parent_subtopics:
            if language == 'de':
                children = [f"{parent} Komponente 1", f"{parent} Komponente 2", f"{parent} Anwendung"]
                fallback_suggestions[parent] = children
                # Füge generische Beziehungslabels hinzu
                relationship_labels = {}
                for child in children:
                    relationship_labels[child] = f"ist ein Bestandteil von {parent}"
                fallback_suggestions[f"{parent}_relationships"] = relationship_labels
            else:
                children = [f"{parent} Component 1", f"{parent} Component 2", f"{parent} Application"]
                fallback_suggestions[parent] = children
                # Füge generische Beziehungslabels hinzu
                relationship_labels = {}
                for child in children:
                    relationship_labels[child] = f"is a component of {parent}"
                fallback_suggestions[f"{parent}_relationships"] = relationship_labels
        
        return fallback_suggestions
