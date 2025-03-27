#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PyLint-Fehlerbehebungsskript für das HackTheStudy-Backend.
Führt automatische Korrekturen für häufige PyLint-Fehler durch.
"""

import os
import sys
import glob
import re
import autopep8
from pathlib import Path

def add_newline_at_end(file_path):
    """Fügt eine Leerzeile am Ende der Datei hinzu, falls nicht vorhanden."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    if not content.endswith('\n'):
        with open(file_path, 'a', encoding='utf-8') as file:
            file.write('\n')
        print(f"✅ Zeilenumbruch am Ende hinzugefügt: {file_path}")
        return True
    return False

def fix_long_lines(file_path):
    """Behebt zu lange Zeilen mit autopep8."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        fixed_content = autopep8.fix_code(
            content, 
            options={
                'max_line_length': 120,
                'aggressive': 1
            }
        )
        
        if fixed_content != content:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(fixed_content)
            print(f"✅ Lange Zeilen korrigiert: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"❌ Fehler beim Beheben langer Zeilen in {file_path}: {e}")
        return False

def fix_f_string_logging(file_path):
    """
    Konvertiert f-String-Logging zu %-Formatierung.
    z.B. logger.info(f"Value: {value}") -> logger.info("Value: %s", value)
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Regex, um f-String-Logging zu erkennen und zu ersetzen
    pattern = r'(logger\.\w+)\(f[\"\'](.*?)[\"\'](?:\s*%\s*\(.*?\))?\)'
    
    def replace_f_string(match):
        logger_call = match.group(1)
        f_string = match.group(2)
        
        # Ersetze {var} durch %s und extrahiere Variablen
        vars_in_string = re.findall(r'\{([^{}]*?)\}', f_string)
        string_with_percent = re.sub(r'\{([^{}]*?)\}', '%s', f_string)
        
        if vars_in_string:
            return f'{logger_call}("{string_with_percent}", {", ".join(vars_in_string)})'
        else:
            return f'{logger_call}("{string_with_percent}")'
    
    new_content = re.sub(pattern, replace_f_string, content)
    
    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(new_content)
        print(f"✅ F-String-Logging korrigiert: {file_path}")
        return True
    return False

def fix_imports(file_path):
    """Ordnet die Imports nach System, Drittanbieter und lokalen Modulen."""
    try:
        # Wir verwenden isort, falls vorhanden, ansonsten machen wir nichts
        try:
            import isort
            isort.file(file_path)
            print(f"✅ Imports neu angeordnet: {file_path}")
            return True
        except ImportError:
            print("⚠️ isort nicht installiert, überspringe Import-Sortierung")
            return False
    except Exception as e:
        print(f"❌ Fehler beim Sortieren der Imports in {file_path}: {e}")
        return False

def fix_file(file_path, only_critical=False):
    """Wendet alle Fehlerbehebungen auf eine Datei an."""
    print(f"\nBearbeite Datei: {file_path}")
    changes = 0
    
    # Kritische Fehler beheben
    changes += int(add_newline_at_end(file_path))
    
    if not only_critical:
        # Stilprobleme beheben
        changes += int(fix_long_lines(file_path))
        changes += int(fix_f_string_logging(file_path))
        changes += int(fix_imports(file_path))
    
    if changes > 0:
        print(f"✅ {changes} Probleme in {file_path} behoben")
    else:
        print(f"ℹ️ Keine Probleme in {file_path} gefunden")
    
    return changes

def main():
    """Hauptfunktion."""
    # Zum Backend-Verzeichnis wechseln
    backend_dir = Path(__file__).parent.absolute()
    os.chdir(backend_dir)
    
    print("=== PyLint-Fehlerbehebung für HackTheStudy-Backend ===")
    
    # Alle Python-Dateien im main-Verzeichnis finden
    main_py_files = glob.glob('main/**/*.py', recursive=True)
    
    # Alle Python-Dateien im worker-Verzeichnis finden
    worker_py_files = glob.glob('worker/**/*.py', recursive=True)
    
    all_files = main_py_files + worker_py_files
    total_changes = 0
    
    print(f"Gefundene Python-Dateien: {len(all_files)}")
    
    # Zuerst kritische Fehler in allen Dateien beheben
    print("\n=== Behebe kritische Fehler ===")
    for file_path in all_files:
        total_changes += fix_file(file_path, only_critical=True)
    
    # Dann Stilprobleme in allen Dateien beheben
    print("\n=== Behebe Stilprobleme ===")
    for file_path in all_files:
        total_changes += fix_file(file_path)
    
    print(f"\n=== Fertig: {total_changes} Probleme in {len(all_files)} Dateien behoben ===")
    
    # Jetzt PyLint ausführen, um zu sehen, ob die Probleme behoben wurden
    print("\n=== Führe PyLint aus ===")
    os.system("python lint.py")

if __name__ == '__main__':
    main() 