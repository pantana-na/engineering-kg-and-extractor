# ==============================================================================
# Unified Production Container Image:
#   - Cloud Run Service: `okf-engineering-workbench` (`unified_web.server:app`)
#   - Cloud Run Job:     `okf-pipeline-job` (`python -m scripts.pipeline_job_runner`)
# Complies with Rule 6 (Non-root runtime user, /healthz) & SPEC-20261120-UNIFIED-WORKBENCH-V2
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    GOOGLE_GENAI_USE_VERTEXAI=true \
    GEMINI_LOCATION=global \
    GEMINI_MODEL=gemini-4-argon \
    EXTRACTER_DEFAULT_MODEL=gemini-4-carbon \
    QUERY_DEFAULT_MODEL=gemini-4-hydrogen \
    ALLOWED_GEMINI_MODELS=gemini-4-carbon,gemini-4-hydrogen,gemini-4-argon,gemini-4-neon \
    SPANNER_NATIVE_EMBEDDING_MODE=native_ml_predict \
    OUTPUT_BUNDLE_DIR=/tmp/okf_bundle \
    JOB_STATUS_DIR=/tmp/okf_job_status \
    APP_MODULE=unified_web.server:app

WORKDIR /app

# Copy project metadata and source code (zero local reference/raw or pre-baked bundles)
COPY pyproject.toml README.md ./
COPY extracter_agent ./extracter_agent
COPY query_agent ./query_agent
COPY unified_web ./unified_web
COPY scripts ./scripts
COPY docs ./docs

# Install poppler-utils (pdftoppm for 300-DPI P&ID rasterization), runtime deps, and non-root user
RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install --no-cache-dir . uvicorn fastapi && \
    groupadd --gid 10001 nonroot && \
    useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin nonroot && \
    mkdir -p /tmp/okf_bundle /tmp/okf_job_status && \
    chown -R nonroot:nonroot /app /tmp/okf_bundle /tmp/okf_job_status

USER nonroot

EXPOSE 8080

CMD ["sh", "-c", "uvicorn ${APP_MODULE:-unified_web.server:app} --host 0.0.0.0 --port ${PORT:-8080}"]
