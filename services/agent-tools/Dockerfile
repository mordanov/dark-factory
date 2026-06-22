FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONUNBUFFERED=1

# Sidecar exposes health + auth adapter on port 8000 (matches unified compose convention)
CMD ["uvicorn", "src.sidecar:app", "--host", "0.0.0.0", "--port", "8000"]
