FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2-binary's runtime libpq and bcrypt's C extension.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the embedding model at build time so the first chat after a cold start does not wait for it.
ENV FASTEMBED_CACHE_PATH=/app/.fastembed
RUN python -c "from fastembed import TextEmbedding; list(TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/app/.fastembed').embed(['warm up']))"

COPY api/ ./api/
COPY agents/ ./agents/
COPY models.py database.py approval.py ./

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
