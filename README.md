# HackTheStudy

A platform for students to analyze exams, generate flashcards, and prepare for tests.

## New Features

### OAuth Authentication

The application now supports OAuth authentication with Google and GitHub. Users can sign in using their existing accounts without creating a new username and password.

### User History

All user activities are now tracked and displayed in the user's dashboard. This includes:
- Exam uploads
- Flashcard generation
- Test simulations
- Concept mapping
- Payment transactions

### Payment System

Users can now purchase credits to use the platform's features. The payment system supports:
- Credit card payments
- PayPal
- Bank transfers
- Transaction history

## Setup Instructions

### Backend Setup

1. Install the required dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Set up the environment variables in `.env`:
```
FLASK_SECRET_KEY=your-secret-key
DATABASE_URL=your-database-url
OPENAI_API_KEY=your-openai-api-key

# OAuth Configuration
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret

# Payment Configuration
STRIPE_SECRET_KEY=your-stripe-secret-key
STRIPE_PUBLISHABLE_KEY=your-stripe-publishable-key

# Frontend URL for OAuth callback
FRONTEND_URL=http://localhost:8080
```

3. Initialize the database with the new tables:
```bash
python init_oauth_db.py
```

4. Start the backend server:
```bash
python app.py
```

### Frontend Setup

1. Install the required dependencies:
```bash
cd frontend
npm install
```

2. Set up the environment variables in `.env`:
```
VITE_API_URL=http://localhost:5000
```

3. Start the frontend development server:
```bash
npm run dev
```

## OAuth Setup

### Google OAuth

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "OAuth client ID"
5. Set the application type to "Web application"
6. Add authorized redirect URIs:
   - `http://localhost:5000/auth/callback/google`
7. Copy the Client ID and Client Secret to your `.env` file

### GitHub OAuth

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Click "New OAuth App"
3. Fill in the application details
4. Set the authorization callback URL to:
   - `http://localhost:5github000/auth/callback/`
5. Copy the Client ID and Client Secret to your `.env` file

## Payment System Setup

For development and testing, the payment system is set up to simulate successful payments without actually charging any cards. In a production environment, you would need to:

1. Create a [Stripe](https://stripe.com/) account
2. Get your API keys from the Stripe dashboard
3. Add the keys to your `.env` file
4. Update the payment processing logic in `backend/api/auth.py` to use the Stripe API

## Usage

1. Sign in using Google or GitHub
2. Purchase credits from the dashboard
3. Use the platform's features (upload exams, generate flashcards, etc.)
4. View your activity history and payment history in the dashboard

## Demo Account

For testing purposes, a demo account is created when you initialize the database:

- Email: demo@example.com
- Name: Demo User
- Credits: 500

## Docker-Setup

Das Projekt kann mit Docker ausgeführt werden, was die Einrichtung der Entwicklungsumgebung vereinfacht.

### Voraussetzungen

- Docker und Docker Compose müssen installiert sein

### Erste Schritte mit Docker

1. Kopieren Sie die `.env.example` Datei und benennen Sie sie in `.env` um:
   ```
   cp .env.example .env
   ```

2. Passen Sie die Umgebungsvariablen in der `.env` Datei an Ihre Anforderungen an

3. Bauen und starten Sie die Container:
   ```
   docker-compose up -d
   ```

4. Das Frontend ist unter http://localhost erreichbar
   Das Backend-API ist unter http://localhost/api verfügbar
   PGAdmin ist unter http://localhost:8081 verfügbar (Login: admin@admin.com / admin123)

### Entwicklung mit Docker

- Logs anzeigen:
  ```
  docker-compose logs -f
  ```

- Container neustarten:
  ```
  docker-compose restart
  ```

- Container stoppen:
  ```
  docker-compose down
  ```

- Container neustarten und neu bauen (nach Änderungen an Abhängigkeiten):
  ```
  docker-compose up -d --build
  ```
