# HackTheStudy - Moodle Exam Analyzer

Eine Webanwendung für Studenten zum Analysieren von Moodle-Prüfungen, Erstellen von Karteikarten und Generieren von Testsimulationen.

## Funktionen

- **Datei-Upload**: Hochladen von bis zu 5 Dateien (.txt oder .pdf) gleichzeitig
- **KI-Analyse**: Analyse der Prüfungsinhalte mit einer KI (Hugging Face API)
- **Karteikarten**: Automatische Erstellung von Karteikarten im Format "Frage: Antwort"
- **Testsimulationen**: Generierung neuer Testfragen zu ähnlichen Themen
- **Temporäre Verarbeitung**: Keine dauerhafte Speicherung der hochgeladenen Dateien

## Technologien

### Frontend
- React mit TypeScript
- Tailwind CSS für das Styling
- React Query für API-Anfragen
- Axios für HTTP-Requests

### Backend
- Flask (Python)
- Hugging Face Inference API für KI-Funktionalitäten
- PyPDF2 für PDF-Verarbeitung

## Installation und Ausführung

### Voraussetzungen
- Node.js und npm
- Python 3.8 oder höher
- pip (Python Package Manager)

### Backend einrichten

1. Ins Backend-Verzeichnis wechseln:
   ```
   cd backend
   ```

2. Virtuelle Umgebung erstellen und aktivieren (optional, aber empfohlen):
   ```
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. Abhängigkeiten installieren:
   ```
   pip install -r requirements.txt
   ```

4. Hugging Face API-Key setzen (optional):
   ```
   # Windows
   set HUGGING_FACE_API_KEY=dein_api_key
   
   # macOS/Linux
   export HUGGING_FACE_API_KEY=dein_api_key
   ```
   
   Hinweis: Wenn kein API-Key gesetzt wird, verwendet die Anwendung Beispieldaten.

5. Server starten:
   ```
   python app.py
   ```
   
   Der Backend-Server läuft dann auf http://localhost:5000

### Frontend einrichten

1. Ins Frontend-Verzeichnis wechseln:
   ```
   cd frontend
   ```

2. Abhängigkeiten installieren:
   ```
   npm install
   ```

3. Entwicklungsserver starten:
   ```
   npm run dev
   ```
   
   Die Frontend-Anwendung läuft dann auf http://localhost:5173

## Deployment

### Backend (PythonAnywhere)

1. Erstelle einen Account auf PythonAnywhere
2. Lade die Backend-Dateien hoch
3. Installiere die Abhängigkeiten mit pip
4. Konfiguriere eine WSGI-Datei, die auf die Flask-App verweist
5. Setze die Umgebungsvariable für den Hugging Face API-Key

### Frontend (Netlify)

1. Erstelle einen Account auf Netlify
2. Verbinde dein GitHub-Repository
3. Setze den Build-Befehl auf `cd frontend && npm install && npm run build`
4. Setze das Publish-Verzeichnis auf `frontend/dist`
5. Konfiguriere die Umgebungsvariable `VITE_API_URL` mit der URL deines Backend-Servers

## Projektstruktur

```
HackTheStudy/
├── backend/
│   ├── app.py                 # Flask-Server und API-Endpunkte
│   └── requirements.txt       # Python-Abhängigkeiten
└── frontend/
    ├── public/                # Statische Dateien
    ├── src/
    │   ├── components/        # React-Komponenten
    │   │   ├── ExamUploader.tsx
    │   │   ├── FlashcardGenerator.tsx
    │   │   ├── TestSimulator.tsx
    │   │   └── ...
    │   ├── pages/             # Seitenkomponenten
    │   │   └── Index.tsx
    │   ├── App.tsx            # Hauptanwendungskomponente
    │   └── main.tsx           # Einstiegspunkt
    ├── package.json           # npm-Abhängigkeiten
    └── ...
```

## Lizenz

MIT
