"""
Hilfsfunktionen zur Textextraktion aus verschiedenen Dokumenttypen.
"""
import io
import logging
import traceback

logger = logging.getLogger(__name__)

def extract_text_from_file(file_name, file_content):
    """
    Extrahiert Text aus verschiedenen Dateiformaten.
    
    Args:
        file_name: Der Name der Datei zur Bestimmung des Typs
        file_content: Der Inhalt der Datei als Bytes
        
    Returns:
        str: Der extrahierte Text
    """
    try:
        # Prüfe auf leere Datei
        if len(file_content) == 0:
            logger.warning(f"Leere Datei: {file_name}")
            return "ERROR: Die Datei ist leer"
            
        # Begrenze die Größe
        max_file_size = 20 * 1024 * 1024  # 20 MB
        if len(file_content) > max_file_size:
            logger.warning(f"Datei zu groß: {file_name} ({len(file_content) // (1024*1024)} MB)")
            return f"ERROR: Die Datei ist zu groß ({len(file_content) // (1024*1024)} MB)"
        
        file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
        
        # Ausführliche Protokollierung für alle Operationen
        logger.info(f"Verarbeite Datei: {file_name} (Typ: {file_ext}, Größe: {len(file_content)} Bytes)")
        
        if file_ext == 'pdf':
            # Verwende PyMuPDF für PDF-Extraktion
            try:
                import fitz  # PyMuPDF
                return extract_text_from_pdf(file_content)
            except Exception as e:
                logger.error(f"Fehler bei der PDF-Extraktion: {str(e)}")
                return f"ERROR: Fehler bei der PDF-Extraktion: {str(e)}"
                
        elif file_ext == 'txt':
            try:
                return file_content.decode('utf-8', errors='replace')
            except Exception as e:
                logger.error(f"Fehler beim Dekodieren der TXT-Datei: {str(e)}")
                return f"ERROR: Textdatei konnte nicht dekodiert werden: {str(e)}"
                
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
    
    except RuntimeError as rt_err:
        # Detaillierte Protokollierung für RuntimeErrors
        stack_trace = traceback.format_exc()
        logger.critical(f"Kritischer RuntimeError bei der Textextraktion: {str(rt_err)}\n{stack_trace}")
        return f"CRITICAL_ERROR: RuntimeError bei der Textextraktion: {str(rt_err)}"
        
    except Exception as e:
        # Allgemeine Fehlerbehandlung mit Stacktrace
        stack_trace = traceback.format_exc()
        logger.error(f"Fehler beim Extrahieren von Text aus {file_name}: {str(e)}\n{stack_trace}")
        return f"ERROR: Fehler beim Lesen der Datei: {str(e)}"

def extract_text_from_pdf(file_data):
    """Extrahiert Text aus einer PDF-Datei mit PyMuPDF."""
    try:
        import fitz  # PyMuPDF
        
        # Sammle extrahierten Text
        all_text = []
        
        # Öffne das PDF als Speicherobjekt
        with io.BytesIO(file_data) as data:
            try:
                # Öffne das PDF-Dokument
                pdf_document = fitz.open(stream=data, filetype="pdf")
                
                # Extrahiere Text von jeder Seite
                for page_num in range(len(pdf_document)):
                    try:
                        page = pdf_document.load_page(page_num)
                        # Verwende einfache Textextraktion
                        text = page.get_text("text")
                        if text:
                            all_text.append(text)
                    except Exception as page_error:
                        logger.warning(f"Fehler bei der Extraktion der Seite {page_num+1}: {str(page_error)}")
                        continue
                
                # Schliesse das Dokument
                pdf_document.close()
            except Exception as e:
                logger.warning(f"Fehler bei der Extraktion mit PyMuPDF: {str(e)}")
                return f"CORRUPTED_PDF: {str(e)}"
        
        # Kombiniere den gesamten Text
        final_text = "\n\n".join([text for text in all_text if text.strip()])
        
        # Wenn noch immer kein Text, gib einen klaren Hinweis zurück
        if not final_text.strip():
            return "Der Text konnte aus dieser PDF nicht extrahiert werden. Es könnte sich um eine gescannte PDF ohne OCR handeln."
        
        # Minimale Bereinigung - nur NUL-Bytes entfernen
        final_text = final_text.replace('\x00', '')
        
        return final_text
    except Exception as e:
        logger.error(f"Kritischer Fehler bei PDF-Extraktion: {str(e)}")
        return f"CORRUPTED_PDF: {str(e)}" 