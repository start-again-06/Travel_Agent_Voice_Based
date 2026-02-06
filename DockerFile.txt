# Production Dockerfile for Voice Travel Agent
# Optimized for fast startup with model pre-caching

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download sentence-transformers model to avoid startup delay
# This downloads the model during build, not runtime
RUN python -c "from sentence_transformers import SentenceTransformer; \
    print('Downloading sentence-transformers model...'); \
    model = SentenceTransformer('all-MiniLM-L6-v2', cache_folder='/app/models'); \
    print('Model downloaded successfully')"

# Copy application code
COPY . .

# Set environment variables for model caching
ENV TRANSFORMERS_CACHE=/app/models
ENV HF_HOME=/app/models
ENV SENTENCE_TRANSFORMERS_HOME=/app/models
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8001/api/ready')" || exit 1

# Run the application
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8001"]
