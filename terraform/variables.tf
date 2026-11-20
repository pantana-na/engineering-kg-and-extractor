variable "project_id" {
  description = "Target Google Cloud project ID"
  type        = string
  default     = "your-gcp-project-id"
}

variable "region" {
  description = "Target Google Cloud region"
  type        = string
  default     = "asia-southeast1"
}

variable "environment" {
  description = "Deployment environment name (nonprod or prod)"
  type        = string
  default     = "nonprod"
}

variable "gemini_model" {
  description = "Default Vertex AI Gemini model identifier"
  type        = string
  default     = "gemini-4-argon"
}

variable "cloudbuild_service_account" {
  description = "Cloud Build service account email or resource URI (defaults to project Compute Engine SA; overrideable via .env)"
  type        = string
  default     = "000000000000-compute@developer.gserviceaccount.com"
}

variable "bucket_name" {
  description = "GCS bucket name for OKF knowledge bundles"
  type        = string
  default     = "your-gcp-project-id-okf-knowledge"
}

variable "spanner_instance_id" {
  description = "Cloud Spanner instance ID for OKF Graph-RAG & Data Lineage"
  type        = string
  default     = "okf-knowledge-spanner"
}

variable "spanner_database_id" {
  description = "Cloud Spanner database ID for OKF Knowledge Graph"
  type        = string
  default     = "okf_knowledge_graph"
}

variable "spanner_processing_units" {
  description = "Cloud Spanner granular processing units (100 PU minimum)"
  type        = number
  default     = 100
}

variable "extracter_web_image" {
  description = "Artifact Registry container image for the OKF Extraction Workbench UI (extracter-agent-web)"
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/your-gcp-project-id/cloud-run-source-deploy/extracter-agent-web:latest"
}

variable "query_web_image" {
  description = "Artifact Registry container image for the OKF Spanner Retrieval Workbench UI (okf-query-agent-web)"
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/your-gcp-project-id/cloud-run-source-deploy/okf-query-agent-web:latest"
}

# ==============================================================================
# Shared & Per-Web-App Cloud Run Runtime SA, Networking, Native IAP & VPC Egress
# ==============================================================================

variable "cloud_run_service_account" {
  description = "Shared default Cloud Run runtime service account email (empty falls back to google_service_account.extracter_agent_sa.email)"
  type        = string
  default     = ""
}

variable "cloud_run_ingress" {
  description = "Shared default Cloud Run ingress: INGRESS_TRAFFIC_ALL (default) | INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER | INGRESS_TRAFFIC_INTERNAL_ONLY"
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
}

variable "cloud_run_security_mode" {
  description = "Shared default Cloud Run security mode: iap (default: IAM + Cloud Run Native IAP) | iam | unauthenticated"
  type        = string
  default     = "iap"
}

variable "cloud_run_vpc_mode" {
  description = "Shared default Cloud Run VPC mode: direct (default: Direct VPC Egress) | connector (Serverless VPC Access Connector) | none"
  type        = string
  default     = "direct"
}

variable "cloud_run_vpc_egress" {
  description = "Shared default Cloud Run VPC egress: ALL_TRAFFIC (default) | PRIVATE_RANGES_ONLY"
  type        = string
  default     = "ALL_TRAFFIC"
}

variable "cloud_run_vpc_network" {
  description = "Shared VPC network name for Direct VPC Egress"
  type        = string
  default     = "default"
}

variable "cloud_run_vpc_subnet" {
  description = "Shared VPC subnetwork name for Direct VPC Egress"
  type        = string
  default     = "default"
}

variable "cloud_run_vpc_connector" {
  description = "Shared Serverless VPC Access Connector ID when vpc_mode = 'connector'"
  type        = string
  default     = ""
}

# Per-App Overrides for Web App 1 (extracter-agent-web) — empty inherits shared cloud_run_*
variable "extracter_web_service_account" {
  description = "Optional Cloud Run runtime service account override for extracter-agent-web"
  type        = string
  default     = ""
}

variable "extracter_web_ingress" {
  description = "Optional ingress override for extracter-agent-web"
  type        = string
  default     = ""
}

variable "extracter_web_security_mode" {
  description = "Optional security mode override for extracter-agent-web (iap | iam | unauthenticated)"
  type        = string
  default     = ""
}

variable "extracter_web_vpc_mode" {
  description = "Optional VPC mode override for extracter-agent-web (direct | connector | none)"
  type        = string
  default     = ""
}

variable "extracter_web_vpc_egress" {
  description = "Optional VPC egress override for extracter-agent-web (ALL_TRAFFIC | PRIVATE_RANGES_ONLY)"
  type        = string
  default     = ""
}

variable "extracter_web_vpc_network" {
  description = "Optional Direct VPC network override for extracter-agent-web"
  type        = string
  default     = ""
}

variable "extracter_web_vpc_subnet" {
  description = "Optional Direct VPC subnetwork override for extracter-agent-web"
  type        = string
  default     = ""
}

variable "extracter_web_vpc_connector" {
  description = "Optional Serverless VPC Access Connector override for extracter-agent-web"
  type        = string
  default     = ""
}

# Per-App Overrides for Web App 2 (okf-query-agent-web) — empty inherits shared cloud_run_*
variable "query_web_service_account" {
  description = "Optional Cloud Run runtime service account override for okf-query-agent-web"
  type        = string
  default     = ""
}

variable "query_web_ingress" {
  description = "Optional ingress override for okf-query-agent-web"
  type        = string
  default     = ""
}

variable "query_web_security_mode" {
  description = "Optional security mode override for okf-query-agent-web (iap | iam | unauthenticated)"
  type        = string
  default     = ""
}

variable "query_web_vpc_mode" {
  description = "Optional VPC mode override for okf-query-agent-web (direct | connector | none)"
  type        = string
  default     = ""
}

variable "query_web_vpc_egress" {
  description = "Optional VPC egress override for okf-query-agent-web (ALL_TRAFFIC | PRIVATE_RANGES_ONLY)"
  type        = string
  default     = ""
}

variable "query_web_vpc_network" {
  description = "Optional Direct VPC network override for okf-query-agent-web"
  type        = string
  default     = ""
}

variable "query_web_vpc_subnet" {
  description = "Optional Direct VPC subnetwork override for okf-query-agent-web"
  type        = string
  default     = ""
}

variable "query_web_vpc_connector" {
  description = "Optional Serverless VPC Access Connector override for okf-query-agent-web"
  type        = string
  default     = ""
}

# ==============================================================================
# Shared & Per-Web-App Cloud Run Compute Sizing, Concurrency, Timeout & Scaling
# ==============================================================================

variable "cloud_run_cpu" {
  description = "Shared default Cloud Run vCPU allocation per container instance (1 | 2 | 4 | 6 | 8)"
  type        = string
  default     = "4"
}

variable "cloud_run_memory" {
  description = "Shared default Cloud Run memory allocation per container instance (e.g., 2Gi | 4Gi | 8Gi | 16Gi)"
  type        = string
  default     = "8Gi"
}

variable "cloud_run_concurrency" {
  description = "Shared default maximum concurrent requests per Cloud Run container instance (1..1000)"
  type        = number
  default     = 30
}

variable "cloud_run_timeout_seconds" {
  description = "Shared default Cloud Run request timeout in seconds (1..3600)"
  type        = number
  default     = 900
}

variable "cloud_run_min_instances" {
  description = "Shared default minimum warm Cloud Run container instances (>= 0; 0 enables scale-to-zero)"
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Shared default maximum autoscaling Cloud Run container instances (null defaults to 3 in nonprod, 5 in prod)"
  type        = number
  default     = null
}

variable "extracter_web_cpu" {
  description = "Optional vCPU override for extracter-agent-web"
  type        = string
  default     = ""
}

variable "extracter_web_memory" {
  description = "Optional memory override for extracter-agent-web"
  type        = string
  default     = ""
}

variable "extracter_web_concurrency" {
  description = "Optional request concurrency override for extracter-agent-web"
  type        = number
  default     = null
}

variable "extracter_web_timeout_seconds" {
  description = "Optional request timeout (seconds) override for extracter-agent-web"
  type        = number
  default     = null
}

variable "extracter_web_min_instances" {
  description = "Optional minimum warm instances override for extracter-agent-web"
  type        = number
  default     = null
}

variable "extracter_web_max_instances" {
  description = "Optional maximum autoscaling instances override for extracter-agent-web"
  type        = number
  default     = null
}

variable "query_web_cpu" {
  description = "Optional vCPU override for okf-query-agent-web"
  type        = string
  default     = ""
}

variable "query_web_memory" {
  description = "Optional memory override for okf-query-agent-web"
  type        = string
  default     = ""
}

variable "query_web_concurrency" {
  description = "Optional request concurrency override for okf-query-agent-web"
  type        = number
  default     = null
}

variable "query_web_timeout_seconds" {
  description = "Optional request timeout (seconds) override for okf-query-agent-web"
  type        = number
  default     = null
}

variable "query_web_min_instances" {
  description = "Optional minimum warm instances override for okf-query-agent-web"
  type        = number
  default     = null
}

variable "query_web_max_instances" {
  description = "Optional maximum autoscaling instances override for okf-query-agent-web"
  type        = number
  default     = null
}

# ==============================================================================
# Unified Workbench v2, Pipeline Job & Spanner Native Embedding Variables
# ==============================================================================

variable "enable_apis" {
  description = "Idempotently enable all required GCP APIs via google_project_service"
  type        = bool
  default     = true
}

variable "cost_center" {
  description = "FinOps cost allocation label value"
  type        = string
  default     = "engineering-ai"
}

variable "artifact_registry_repo" {
  description = "Artifact Registry Docker repository ID for unified container image"
  type        = string
  default     = "okf-workbench"
}

variable "unified_web_service_name" {
  description = "Base Cloud Run service name for unified OKF Engineering Workbench"
  type        = string
  default     = "okf-engineering-workbench"
}

variable "unified_web_image" {
  description = "Artifact Registry container image URI for unified workbench & pipeline job"
  type        = string
  default     = ""
}

variable "pipeline_job_name" {
  description = "Base Cloud Run Job name for parameterized batch extraction & Spanner sync"
  type        = string
  default     = "okf-pipeline-job"
}

variable "pipeline_job_timeout_seconds" {
  description = "Cloud Run Job task timeout in seconds (default 3600 = 1 hour, max 86400)"
  type        = number
  default     = 3600
}

variable "extracter_default_model" {
  description = "Default Gemini 4 model for Extractor Studio & batch extraction"
  type        = string
  default     = "gemini-4-carbon"
}

variable "query_default_model" {
  description = "Default Gemini 4 model for Knowledge Graph & Query Workbench"
  type        = string
  default     = "gemini-4-hydrogen"
}

variable "allowed_gemini_models" {
  description = "Comma-separated allowlist of selectable Gemini 4 models"
  type        = string
  default     = "gemini-4-carbon,gemini-4-hydrogen,gemini-4-argon,gemini-4-neon"
}

variable "spanner_native_embedding_mode" {
  description = "Spanner embedding execution mode: native_ml_predict | client_sdk"
  type        = string
  default     = "native_ml_predict"
}
