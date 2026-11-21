# Google Secure AI Framework (SAIF & SAIF 2.0): 6 Elements, 15 Risks & Autonomous Agent Controls Reference

**Authoritative Primary Sources:**
- **Google Safety Center — SAIF Hub:** `https://safety.google/intl/en/safety/saif/`
- **Interactive SAIF Portal & Risk/Control Catalog:** `https://saif.google/` (`https://github.com/google/saif-data`)
- **SAIF 2.0 Agentic AI Security Whitepaper:** *Google's Approach for Secure AI Agents: An Introduction* (`https://storage.googleapis.com/gweb-research2023-media/pubtools/1018686.pdf`)
- **Google Cloud Model Armor & SCC AI Protection:** `https://cloud.google.com/security-command-center/docs/model-armor-overview` & `https://cloud.google.com/security-command-center/docs/ai-protection-overview`

---

## 1. The 6 Core Elements of Google SAIF

| # | Official SAIF Core Element | Architectural Mandate & Native Google Cloud Controls |
| :- | :--- | :--- |
| **1** | **Expand strong security foundations to the AI ecosystem** | Extend Zero Trust, encryption at rest/in transit/in use (**CMEK / Cloud HSM / Confidential Computing**), network perimeters (**VPC Service Controls + Private Service Connect**), least-privilege IAM, and **SLSA Level 3 + Binary Authorization** to datasets, RAG indexes, prompts, models, and agent runtimes. |
| **2** | **Extend detection and response to bring AI into an organization's threat universe** | Integrate AI telemetry (prompt/response hashes, **Model Armor** verdicts, ADK tool trajectories, token spikes) and **Security Command Center (SCC) AI Protection** posture/threat findings into **Cloud Logging** and **Google SecOps (SIEM/SOAR)** with AI incident response playbooks. |
| **3** | **Automate defenses to keep pace with existing and new threats** | Enforce machine-speed inline defenses: **Model Armor** (prompt injection, jailbreak, malicious URL, CSAM/RAI screening), **Sensitive Data Protection (Cloud DLP)** (automated PII/PCI tokenization/redaction), pre-build **CodeMender** SAST, and automated CI/CD adversarial eval gates (`agents-cli eval`). |
| **4** | **Harmonize platform-level controls to ensure consistent security across the organization** | Standardize security at the platform layer across all teams: org-wide **Model Armor floor templates**, shared **VPC-SC** perimeters, centralized **Secret Manager / Cloud KMS** governance, and standardized ADK security callback modules. |
| **5** | **Adapt controls to adjust mitigations and create faster feedback loops for AI deployment** | Establish a continuous feedback loop connecting live production telemetry, HITL overrides, and red-team discoveries into **atomic versioned bundles** (Prompt + Tool Schema + Pinned Model ID + Golden Eval Dataset) with canary rollouts and instant rollback. |
| **6** | **Contextualize AI system risks in surrounding business processes** | Align technical controls with business blast radius: separate read-only retrieval agents from state-mutating tools, propagate **End-User Identity (`User Auth`)**, enforce deterministic policy/monetary caps, require **externalized HITL approval** for high-value/destructive mutations, and reconcile regulatory WORM retention with privacy erasure via **PII redaction / crypto-shredding**. |

---

## 2. Complete Catalog of the 15 Official SAIF Risks (`google/saif-data`)

Every AI Solution Design and SDD must evaluate and mitigate all 15 standardized SAIF risks across the **Data**, **Infrastructure**, **Model**, and **Application** layers:

| # | SAIF ID | Official Risk Name | Layer(s) | Threat Vector | Mandatory Google Cloud & ADK Mitigation |
| :- | :--- | :--- | :--- | :--- | :--- |
| 1 | **`DP`** | **Data Poisoning** | Data | Injecting malicious, corrupted, or backdoored documents into training sets or RAG grounding corpora. | Restrict write IAM on RAG/data buckets to vetted ingestion SAs; cryptographic SHA-256 document hashing; human/automated approval gates before indexing new corpus versions; Dataplex lineage. |
| 2 | **`UTD`** | **Unauthorized Training Data** | Data | Ingesting unconsented PII/PCI, copyrighted content, or restricted records into training or RAG indexes. | Pre-ingestion **Sensitive Data Protection (Cloud DLP)** inspection/redaction; explicit zero customer-data training guarantees on Vertex AI; Dataplex governance catalogs. |
| 3 | **`EDH`** | **Excessive Data Handling** | Data / App | Over-collecting, caching, or logging unmasked PII/PAN/secrets across prompts, context caches, or traces. | Bidirectional **Cloud DLP** de-identification/tokenization in `before_agent_callback` prior to LLM inference, context caching, `agentengine://` persistence, or Cloud Logging; strict TTL lifecycles. |
| 4 | **`MST`** | **Model Source Tampering** | Infra | Supply-chain compromise of source code, container layers, dependencies, or model weights/serializers. | Pre-build **CodeMender** SAST (`cm find/verify/fix`), **Artifact Analysis**, **SLSA Level 3 build provenance**, Sigstore signing, and **Binary Authorization**. |
| 5 | **`MXF`** | **Model Exfiltration** | Infra | Unauthorized copying or exfiltration of proprietary model weights, adapters, prompts, or RAG corpora. | **VPC Service Controls (VPC-SC)** perimeters blocking external API egress, **CMEK**, least-privilege IAM, and **Confidential Computing** where applicable. |
| 6 | **`MDT`** | **Model Deployment Tampering** | Infra | Unauthorized post-build modification of serving containers, env vars, Model Armor templates, or endpoints. | Immutable Artifact Registry digests, **Binary Authorization**, declarative **Terraform + Infrastructure Manager** with drift detection, and locked runtime SAs. |
| 7 | **`DMS`** | **Denial of ML Service (DoMLS)** | Infra / App | Token-flooding, sponge prompts, or recursive multi-agent loops exhausting quotas (`429`), latency SLOs, or budgets. | **Cloud Armor** rate limiting at edge, per-user/session token & turn budgets in ADK (`max_steps`, wall-clock timeouts), and **Vertex AI Provisioned Throughput + PayGo spillover**. |
| 8 | **`MRE`** | **Model Reverse Engineering** | Model / Infra | Systematic API querying/probing to clone decision boundaries or extract system instructions. | Per-principal rate/volume throttling, suppressing raw logits, hardened system instructions, and **SCC AI Protection** anomaly detection. |
| 9 | **`IIC`** | **Insecure Integrated Component** | Model / App | Vulnerable 3rd-party libraries, RAG parsers, plugins, or unvetted MCP/tool servers wired into the agent. | Dependency CVE scanning (`pip-audit`/`npm audit`/Artifact Analysis), strict tool allowlisting, **SCC AI Protection** agent/MCP inventory, and zero arbitrary code/SQL execution tools. |
| 10 | **`PIJ`** | **Prompt Injection (Direct & Indirect)** | Model / App | **Direct** (adversarial user prompt) or **Indirect** (malicious instructions embedded in retrieved RAG docs, disputes, or tool payloads) hijacking agent behavior. | **Model Armor** inline inspection on BOTH `before_agent_callback`/`before_model_callback` (Direct `PIJ`) AND `after_tool_callback` (Indirect `PIJ`), paired with deterministic downstream authorization. |
| 11 | **`MEV`** | **Model Evasion** | Model | Encoding tricks (Base64, homoglyphs, multilingual ciphering) or adversarial perturbations bypassing safety filters. | Input canonicalization/normalization prior to **Model Armor** inspection, layered safety filters, and continuous adversarial red-teaming in `agents-cli eval`. |
| 12 | **`SDD`** | **Sensitive Data Disclosure** | Model / App | Leaking cross-tenant RAG data, unmasked PII/PCI, or system secrets in model responses or outbound links. | Per-user RAG ACL enforcement via **`User Auth`** token propagation, post-inference **Cloud DLP** scrubbing in `after_model_callback`, and strict URL/Markdown image sanitization. |
| 13 | **`ISD`** | **Inferred Sensitive Data** | Model / App | Statistical or membership inference across responses revealing private attributes of individuals/cohorts. | Scoped row-level data access (agent can only query the authenticated caller's authorized scope), output granularity limits, and query-pattern anomaly monitoring. |
| 14 | **`IMO`** | **Insecure Model Output** | App | Downstream systems or UIs blindly trusting hallucinated citations, unescaped HTML/XSS, or malicious Markdown links. | $1.000$ groundedness requirement with deterministic citation verification, strict Pydantic/JSON schema validation, safe React text escaping, and outbound URL allowlisting. |
| 15 | **`RAC`** | **Rogue Actions** *(Core Agentic Risk)* | App (Agents) | Autonomous agents executing unauthorized writes, excessive refunds, or confused-deputy privilege escalation. | Read-only retrieval principals, **`User Auth`** propagation, deterministic microservice policy/cap validation, **externalized HITL approval gates** outside the LLM context, and idempotency keys. |

---

## 3. SAIF 2.0 Blueprint for Autonomous AI Agents (`google-adk` & `agent_runtime`)

### 3.1 The 3 Non-Negotiable Agent Security Principles
1. **Well-Defined Human Controllers:** Every agent trajectory is initiated by and bound to a cryptographically verified human (or accountable workload) controller. Untrusted data ingested via RAG or tools **never** gains controller privilege.
2. **Carefully Limited Powers (Strict Least Privilege):** Separate read-only informational subagents from action subagents; propagate end-user identity (`User Auth`); enforce deterministic parameter/policy bounds outside the LLM.
3. **Observable Actions & Planning:** Capture tamper-evident structured traces of every prompt hash, retrieved chunk ID, tool call argument, Model Armor verdict, and HITL decision, bounded by explicit step/token budgets.

### 3.2 Mandatory 4-Point ADK Callback & Deterministic Guardrail Architecture

All production ADK agents (`google.adk.agents.Agent` / `LlmAgent`) must wire security callbacks across four interception points:

```python
# Conceptual Blueprint: 4-Point SAIF 2.0 Guardrails in Google ADK
from google.adk.agents import Agent
from google.adk.tools import FunctionTool, ToolContext

# 1. BEFORE AGENT / MODEL: Direct Prompt Injection (Model Armor) + Inbound PII Tokenization (Cloud DLP)
def saif_before_model_guardrail(callback_context, llm_request):
    # Step 1a: Screen raw user prompt via Google Cloud Model Armor (PIJ, Jailbreak, Malicious URL, RAI)
    verdict = model_armor_client.sanitize_user_prompt(llm_request.contents)
    if verdict.filter_match_state == "MATCH_FOUND":
        return create_blocked_response(verdict)  # Deterministic block: zero LLM or tool execution
    # Step 1b: De-identify / tokenize PII, PCI (PAN/CVV), SSN via Sensitive Data Protection (Cloud DLP)
    llm_request.contents = dlp_client.deidentify_with_tokens(llm_request.contents, session_id=callback_context.session_id)
    return None

# 2. AFTER TOOL: Indirect Prompt Injection Screening on Retrieved RAG Chunks & External Tool Outputs
def saif_after_tool_guardrail(tool, args, tool_context: ToolContext, tool_response: dict) -> dict:
    # Screen untrusted retrieved documents / dispute notes / external API payloads via Model Armor
    verdict = model_armor_client.sanitize_model_response_or_context(str(tool_response))
    if verdict.filter_match_state == "MATCH_FOUND":
        return {
            "status": "SECURITY_BLOCKED_INDIRECT_INJECTION",
            "error_code": "SAIF_PIJ_INDIRECT_DETECTED",
            "details": "Untrusted tool/RAG payload contained adversarial instruction patterns and was quarantined."
        }
    return tool_response

# 3. DETERMINISTIC ACTION TOOL: User Auth + Hard Policy Cap + Externalized HITL Verification
def execute_bounded_business_action(
    entity_id: str,
    amount_usd: float,
    idempotency_key: str,
    hitl_approval_token: str,
    tool_context: ToolContext,
) -> dict:
    """Executes a state-mutating business action only after deterministic policy & external HITL verification."""
    # Enforce caller identity (Anti-Confused-Deputy User Auth)
    caller_principal = tool_context.state.get("verified_user_principal")
    if not caller_principal:
        return {"status": "UNAUTHORIZED", "error_code": "MISSING_USER_AUTH"}
    # Enforce deterministic policy cap in code (never rely on prompt instructions alone)
    if amount_usd > MAX_AUTO_OR_TIER_CAP_USD:
        return {"status": "POLICY_CAP_EXCEEDED", "error_code": "CAP_VIOLATION"}
    # Verify cryptographic HITL token signed by the human controller in the UI/API gateway outside LLM context
    if not verify_external_hitl_signature(hitl_approval_token, caller_principal, entity_id, amount_usd, idempotency_key):
        return {"status": "HITL_CONFIRMATION_REQUIRED", "error_code": "AWAITING_EXTERNAL_HITL_SIGNATURE"}
    return core_transactional_service.execute(entity_id, amount_usd, caller_principal, idempotency_key)

# 4. AFTER MODEL: Outbound DLP Scrubbing + Citation Groundedness Check + URL/Origin Allowlist
def saif_after_model_guardrail(callback_context, llm_response):
    # Scrub any residual PII/secrets via Model Armor + Cloud DLP and strip unauthorized Markdown image/link origins
    sanitized_text = model_armor_and_dlp_sanitize_output(llm_response.text)
    sanitized_text = enforce_outbound_url_allowlist(sanitized_text)
    llm_response.text = sanitized_text
    return llm_response
```
