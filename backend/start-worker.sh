#!/bin/bash
echo "Waiting for PostgreSQL to start..."
while ! nc -z db 5432; do
  sleep 1
done
echo "PostgreSQL is ready"

echo "Waiting for Redis to start..."
while ! nc -z redis 6379; do
  sleep 1
done
echo "Redis is ready"

echo "Starting Celery worker..."
# Use the celery instance directly from tasks.py
celery -A tasks.celery worker --loglevel=info
