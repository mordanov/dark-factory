FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Startup: run migrations → seed → uvicorn
CMD ["sh", "-c", "\
  alembic upgrade head && \
  python scripts/seed.py && \
  uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2 \
"]
