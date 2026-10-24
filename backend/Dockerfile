FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# App root ke bajay normal user se chalate hain (security). /data/chroma ChromaDB ka folder hai.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/chroma \
    && chown -R appuser /data

# Pehle sirf requirements copy: code badalne par libraries dobara install nahi hongi (build tez)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER appuser

# ChromaDB ka embedding model build ke waqt download, taaki pehli upload par intezaar na karna pade.
# Fail ho jaye to build nahi rukta; tab model pehli upload par download hoga.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warm up'])" \
    || echo "embedding model pre-download skipped"

EXPOSE 8000

# Cloud platforms PORT environment variable dete hain; nahi mila to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
