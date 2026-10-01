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

variable "query_web_image" {
  description = "Artifact Registry container image for the OKF Spanner Retrieval Workbench UI (okf-query-agent-web)"
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/your-gcp-project-id/cloud-run-source-deploy/okf-query-agent-web:latest"
}
