# Dockerfile - Docker Configuration

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY schema.sql .

# Expose port
EXPOSE 5000

# Environment variables
ENV OLLAMA_URL=http://localhost:11434
ENV HOST=0.0.0.0
ENV PORT=5000
ENV DEBUG=False

# Run application
CMD ["python", "-m", "quart", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
