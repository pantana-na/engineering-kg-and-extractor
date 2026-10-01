# ==============================================================================
# Production Container Image for PIDtoOKF v2 — Mining M3 Light Executive Cockpit
# + Google ADK Agent Runtime Web Server
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    GOOGLE_GENAI_USE_VERTEXAI=true \
    GEMINI_LOCATION=global \
    GEMINI_MODEL=gemini-3.8-flash \
    OUTPUT_BUNDLE_DIR=/tmp/okf_bundle \
    APP_MODULE=extracter_agent.web_server:app

WORKDIR /app

# Copy project metadata and source code (zero local reference/wiki or pre-baked bundles)
COPY pyproject.toml README.md ./
COPY extracter_agent ./extracter_agent
COPY query_agent ./query_agent
COPY docs ./docs

# Install runtime dependencies and create empty runtime bundle directory
RUN pip install --upgrade pip && \
    pip install --no-cache-dir . uvicorn fastapi && \
    mkdir -p /tmp/okf_bundle

EXPOSE 8080

CMD ["sh", "-c", "uvicorn ${APP_MODULE:-extracter_agent.web_server:app} --host 0.0.0.0 --port ${PORT:-8080}"]
