"""Cognitive Model-Driven Query Intent Classifier for OKF Spanner Graph-RAG Agent.

Strictly adheres to Rule 11:
- Cognitive model-driven intent classification using Gemini Flash structured schemas
- ZERO regular expression routing or keyword heuristics
"""

from __future__ import annotations

import os
import time

from google import genai
from google.genai import types

from query_agent.config import get_config
from query_agent.models.intent import (
    QueryIntentCategory,
    QueryIntentClassificationResult,
)

QUERY_INTENT_SYSTEM_PROMPT = """You are the Cognitive Intent Router for the OKF Spanner Graph-RAG & Data Lineage Query Agent.
Analyze the user's engineering question or governance request and classify it strictly into one of the following Canonical Query Intent categories:

1. ENTITY_AND_PARAMETER_LOOKUP: The user asks for specific design parameters, operating conditions, mechanical dimensions, metallurgy, nozzle schedules, or calibrated ranges for a specific equipment tag, instrument tag, piping line, or unit (e.g., "What is the design pressure of R-0201?", "Show parameters for C-0201").
2. HYBRID_SEMANTIC_KEYWORD_SEARCH: The user asks a conceptual engineering question, operating procedure question, troubleshooting question, or chemical hazard / SDS property question requiring hybrid vector + full-text search across OKF section chunks.
3. GRAPH_CONNECTIVITY_TRAVERSAL: The user asks about upstream/downstream process connectivity, feeding/receiving equipment, multi-hop process trains, or instrument control/trip loops (e.g., "Trace 3 hops downstream from R-0201", "Which instruments monitor or trip V-0101?").
4. DATA_LINEAGE_AND_CONFLICT_AUDIT: The user asks for source PDF provenance, MD5 hash, document revision, cross-document conflict audits (`⚠️ CONFLICT`), or forward blast-radius analysis when a raw PDF is revised (e.g., "Which raw PDFs were used to derive R-0201?", "What OKF facts are impacted if PID-23-0013 is revised?").
5. MULTISTAGE_RISK_AND_HAZOP_ANALYSIS: The user asks a multi-stage risk assessment, HAZOP deviation, thermal runaway, overpressure, or safeguard/interlock adequacy question requiring risk matrix tier lookup, cause/consequence analysis, upstream/downstream plant propagation, and safeguard/PSV verification.
6. SYNC_BUNDLE_TO_SPANNER: The user asks to inspect or synchronize the Dataplex Data Catalog, OpenLineage pipeline topology, or Spanner Knowledge Graph ingestion status.
7. OTHERS: Out-of-scope inquiries, general chit-chat, or requests unrelated to chemical plant engineering knowledge or data governance.

Provide explicit step-by-step reasoning and extract any equipment/instrument/line tags or raw PDF document codes mentioned.
"""


class CognitiveQueryClassifier:
    """Cognitive query intent classifier powered by Vertex AI / Gemini."""

    def __init__(self, client: genai.Client | None = None) -> None:
        cfg = get_config()
        self.model_name = cfg.gemini_model
        self._client = client

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            cfg = get_config()
            retry_opts = types.HttpRetryOptions(
                attempts=5,
                initial_delay=2.0,
                max_delay=32.0,
                exp_base=2.0,
                jitter=1.0,
                http_status_codes=[429, 500, 502, 503, 504],
            )
            http_opts = types.HttpOptions(retry_options=retry_opts)
            use_vertex = (
                os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")
                or os.getenv("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() in ("true", "1")
            )
            if use_vertex:
                self._client = genai.Client(
                    vertexai=True,
                    project=cfg.google_cloud_project,
                    location=cfg.gemini_location,
                    http_options=http_opts,
                )
            else:
                self._client = genai.Client(http_options=http_opts)
        return self._client

    def classify_query(self, prompt: str) -> QueryIntentClassificationResult:
        """Classify the user query into a canonical QueryIntentCategory using model-driven reasoning."""
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=QUERY_INTENT_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=QueryIntentClassificationResult,
                        temperature=0.0,
                    ),
                )
                if response.parsed and isinstance(
                    response.parsed, QueryIntentClassificationResult
                ):
                    return response.parsed
                return QueryIntentClassificationResult.model_validate_json(response.text)
            except Exception as exc:
                last_err = exc
                if attempt < 2 and any(
                    code in str(exc) for code in ("500", "503", "429", "INTERNAL", "UNAVAILABLE")
                ):
                    time.sleep(2.0 * (2**attempt))
                    continue
                break
        return QueryIntentClassificationResult(
            intent=QueryIntentCategory.OTHERS,
            confidence=0.0,
            reasoning=f"Model reasoning invocation unavailable: {last_err}",
            target_entities=[],
            raw_sources=[],
        )
