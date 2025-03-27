#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PyLint-Ausführungsskript für das HackTheStudy-Backend.
Führt PyLint mit der konfigurierten pylintrc-Datei aus.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

def parse_args():
    """Parst die Kommandozeilenargumente."""
    parser = argparse.ArgumentParser(description='Führt PyLint für das HackTheStudy-Backend aus.')
    parser.add_argument(
        '--path', 
        default='main worker', 
        help='Pfad der zu prüfenden Dateien/Verzeichnisse (relativ zum Backend-Verzeichnis). Standardmäßig main und worker'
    )
    parser.add_argument(
        '--fix', 
        action='store_true',
        help='Versucht, einige Probleme automatisch zu beheben (mit autopep8)'
    )
    parser.add_argument(
        '--details', 
        action='store_true',
        help='Zeigt detaillierte Fehlerinformationen an'
    )
    parser.add_argument(
        '--threshold', 
        type=float,
        default=7.0,
        help='Minimale Bewertung, um den Test zu bestehen (0-10)'
    )
    return parser.parse_args()

def run_pylint(paths, rcfile, details=False):
    """
    Führt PyLint für die angegebenen Pfade aus.
    
    Args:
        paths (str): Zu prüfende Pfade (Leerzeichen-getrennt)
        rcfile (str): Pfad zur PyLint-Konfigurationsdatei
        details (bool): Ob detaillierte Fehlerinformationen angezeigt werden sollen
        
    Returns:
        tuple: (Rückgabecode, Bewertung)
    """
    print(f"Führe PyLint für {paths} aus...")
    
    # Pfade in Liste aufteilen
    path_list = paths.split()
    
    # Kommando zusammenbauen
    cmd = [
        'pylint',
        '--rcfile', rcfile
    ]
    
    # Detaillierte Fehlerinformationen anzeigen?
    if not details:
        cmd.append('--reports=no')
    
    # Pfade hinzufügen
    cmd.extend(path_list)
    
    # PyLint ausführen
    try:
        process = subprocess.run(
            cmd,
            check=False,
            text=True,
            capture_output=True
        )
        
        # Ausgabe anzeigen
        output = process.stdout
        if process.stderr:
            output += "\n" + process.stderr
            
        print(output)
        
        # Bewertung extrahieren
        rating = 0.0
        for line in output.split('\n'):
            if 'Your code has been rated at ' in line:
                try:
                    rating_str = line.split('Your code has been rated at ')[1].split('/')[0]
                    rating = float(rating_str)
                    break
                except (IndexError, ValueError):
                    pass
        
        return process.returncode, rating
    except Exception as e:
        print(f"Fehler beim Ausführen von PyLint: {e}")
        return 1, 0.0

def run_autopep8(paths):
    """
    Führt autopep8 für die angegebenen Pfade aus.
    
    Args:
        paths (str): Zu korrigierende Pfade (Leerzeichen-getrennt)
        
    Returns:
        int: Rückgabecode
    """
    print(f"Versuche Stilprobleme in {paths} automatisch zu beheben...")
    
    # Pfade in Liste aufteilen
    path_list = paths.split()
    
    try:
        for path in path_list:
            cmd = [
                'autopep8',
                '--in-place',
                '--aggressive',
                '--aggressive',
                '--max-line-length', '120',
                '--recursive',
                path
            ]
            
            process = subprocess.run(
                cmd,
                check=False,
                text=True,
                capture_output=True
            )
            
            # Ausgabe anzeigen
            if process.stdout:
                print(process.stdout)
            if process.stderr:
                print(process.stderr)
        
        return 0
    except Exception as e:
        print(f"Fehler beim Ausführen von autopep8: {e}")
        return 1

def main():
    """Hauptfunktion."""
    args = parse_args()
    
    # Zum Backend-Verzeichnis wechseln
    backend_dir = Path(__file__).parent.absolute()
    os.chdir(backend_dir)
    
    # PyLint-Konfigurationsdatei
    rcfile = os.path.join(backend_dir, 'pylintrc')
    
    # Pfad normalisieren
    paths = args.path
    
    # Automatische Korrekturen durchführen?
    if args.fix:
        print("=== Führe autopep8 für automatische Korrekturen aus ===")
        run_autopep8(paths)
        print("")
    
    # PyLint ausführen
    print("=== Führe PyLint aus ===")
    returncode, rating = run_pylint(paths, rcfile, args.details)
    
    # Bewertung überprüfen
    if rating < args.threshold:
        print(f"\n❌ Test fehlgeschlagen: Bewertung {rating:.2f} liegt unter dem Schwellenwert {args.threshold:.2f}")
        sys.exit(1)
    else:
        print(f"\n✅ Test bestanden: Bewertung {rating:.2f} liegt über dem Schwellenwert {args.threshold:.2f}")
        sys.exit(returncode)

if __name__ == '__main__':
    main() 