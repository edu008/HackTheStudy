"""
Optimierte Textextraktion aus verschiedenen Dokumenttypen.
"""
import io
import logging
import traceback
import fitz  # PyMuPDF direkt importieren für bessere Performance

logger = logging.getLogger(__name__)

def extract_text_from_file(file_name, file_content):
    """
    Extrahiert Text aus verschiedenen Dateiformaten mit optimierter PDF-Verarbeitung.
    
    Args:
        file_name: Der Name der Datei zur Bestimmung des Typs
        file_content: Der Inhalt der Datei als Bytes
        
    Returns:
        str: Der extrahierte Text
    """
    try:
        # Schnelle Überprüfung auf leere Datei
        if not file_content or len(file_content) == 0:
            logger.warning(f"Leere Datei: {file_name}")
            return "ERROR: Die Datei ist leer"
            
        # Größenbegrenzung für die Verarbeitung
        max_file_size = 30 * 1024 * 1024  # 30 MB erhöhtes Limit für größere PDFs
        if len(file_content) > max_file_size:
            logger.warning(f"Datei zu groß: {file_name} ({len(file_content) // (1024*1024)} MB)")
            return f"ERROR: Die Datei ist zu groß ({len(file_content) // (1024*1024)} MB)"
        
        # Dateiendung bestimmen
        file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
        logger.info(f"Verarbeite Datei: {file_name} (Typ: {file_ext}, Größe: {len(file_content)} Bytes)")
        
        # PDF-Verarbeitung mit direktem PyMuPDF
        if file_ext == 'pdf':
            return extract_text_from_pdf_optimized(file_content)
                
        # Textdateien
        elif file_ext == 'txt':
            try:
                return file_content.decode('utf-8', errors='replace')
            except Exception as e:
                logger.error(f"Fehler beim Dekodieren der TXT-Datei: {str(e)}")
                return f"ERROR: Textdatei konnte nicht dekodiert werden: {str(e)}"
                
        # Word-Dokumente
        elif file_ext in ['docx', 'doc']:
            from io import BytesIO
            try:
                logger.info(f"Verarbeite DOCX/DOC: {file_name}")
                import docx
                doc = docx.Document(BytesIO(file_content))
                return "\n".join([paragraph.text for paragraph in doc.paragraphs])
            except Exception as docx_err:
                # Fallback für alte .doc-Dateien
                try:
                    logger.info(f"DOCX-Verarbeitung fehlgeschlagen, versuche DOC-Fallback für {file_name}")
                    from antiword import Document
                    doc = Document(file_content)
                    return doc.getText()
                except Exception as doc_err:
                    logger.error(f"Fehler bei DOC/DOCX-Verarbeitung: {str(docx_err)} / {str(doc_err)}")
                    return f"ERROR: Dokument konnte nicht gelesen werden: {str(doc_err)}"
        else:
            logger.warning(f"Nicht unterstützter Dateityp: {file_ext}")
            return f"ERROR: Dateityp .{file_ext} wird nicht unterstützt."
    
    except Exception as e:
        # Allgemeine Fehlerbehandlung mit detailliertem Logging
        stack_trace = traceback.format_exc()
        logger.error(f"Fehler beim Extrahieren von Text aus {file_name}: {str(e)}\n{stack_trace}")
        return f"ERROR: Fehler beim Lesen der Datei: {str(e)}"

def extract_text_from_pdf_optimized(file_data):
    """
    Optimierte Version der PDF-Textextraktion mit PyMuPDF.
    
    Args:
        file_data: Der Inhalt der PDF-Datei als Bytes
        
    Returns:
        str: Der extrahierte Text
    """
    try:
        # Öffne das PDF direkt im Speicher ohne temporäre Datei
        with io.BytesIO(file_data) as pdf_stream:
            # Öffne PDF mit PyMuPDF (fitz)
            pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")
            
            # Parameter für verbesserte Textextraktion
            extracted_pages = []
            page_count = len(pdf_document)
            
            logger.info(f"PDF hat {page_count} Seiten - starte Extraktion")
            
            # Extrahiere Text von jeder Seite mit optimierten Einstellungen
            for page_num in range(page_count):
                try:
                    # Lade Seite
                    page = pdf_document[page_num]
                    
                    # Verwende get_text mit Optionen für bessere Extraktion
                    # "text" gibt nur den Text zurück, "blocks" würde Textblöcke mit Koordinaten zurückgeben
                    page_text = page.get_text("text")
                    
                    # Füge Text zur Liste hinzu, wenn nicht leer
                    if page_text.strip():
                        extracted_pages.append(page_text)
                        
                except Exception as page_error:
                    logger.warning(f"Fehler bei der Extraktion der Seite {page_num+1}: {str(page_error)}")
                    continue
            
            # Schließe das Dokument
            pdf_document.close()
            
            # Kombiniere den gesamten Text mit Seitenumbrüchen
            if extracted_pages:
                combined_text = "\n\n".join(extracted_pages)
                # Entferne problematische Zeichen (NUL-Bytes etc.)
                combined_text = combined_text.replace('\x00', '')
                logger.info(f"PDF-Extraktion erfolgreich: {len(combined_text)} Zeichen extrahiert")
                return combined_text
            else:
                logger.warning("Keine Textdaten in der PDF gefunden")
                return "Keine Textdaten konnten aus dieser PDF extrahiert werden. Es könnte sich um ein Scan-Dokument ohne OCR handeln."
                
    except Exception as e:
        logger.error(f"Kritischer Fehler bei der PDF-Extraktion: {str(e)}")
        return f"FEHLER: PDF konnte nicht verarbeitet werden: {str(e)}" 