#!/bin/bash

# Wait for the database to be ready
echo "Waiting for PostgreSQL to start..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL is ready"

# Drop all tables in the database
echo "Dropping all existing tables..."
python -c "from app import create_app; app = create_app(); from models import db; app.app_context().push(); db.drop_all()"

# Create database tables anew
echo "Creating database tables..."
python -c "from app import create_app; app = create_app(); from models import db; app.app_context().push(); db.create_all()"

# Start the Flask application
echo "Starting Flask application..."
flask run --host=0.0.0.0