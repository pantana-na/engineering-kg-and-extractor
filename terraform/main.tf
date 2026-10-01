# Terraform Infrastructure for Extracter Agent Knowledge Storage
# Complies with Rule 9 (Infrastructure Manager) & Rule 10 (Zero allUsers)

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# GCS Bucket for OKF Knowledge Bundles
resource "google_storage_bucket" "okf_knowledge_bucket" {
  name                        = "${var.bucket_name}-${var.environment}"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 5
      with_state         = "ARCHIVED"
    }
  }

  labels = {
    environment = var.environment
    managed_by  = "infrastructure-manager"
    app         = "extracter-agent"
  }
}

# Service Account for Extracter Agent Runtime
resource "google_service_account" "extracter_agent_sa" {
  account_id   = "extracter-agent-${var.environment}"
  display_name = "Extracter Agent Service Account (${var.environment})"
}

# Authorize Agent SA to write into GCS Bucket (Rule 10: Zero allUsers)
resource "google_storage_bucket_iam_member" "agent_bucket_admin" {
  bucket = google_storage_bucket.okf_knowledge_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.extracter_agent_sa.email}"
}

# Cloud Spanner Instance for OKF Graph-RAG, Vector, Full-Text & Data Lineage
resource "google_spanner_instance" "okf_knowledge_spanner" {
  name             = "${var.spanner_instance_id}-${var.environment}"
  config           = "regional-${var.region}"
  display_name     = "OKF Graph (${var.environment})"
  processing_units = var.spanner_processing_units
  edition          = "ENTERPRISE"

  labels = {
    environment = var.environment
    managed_by  = "infrastructure-manager"
    app         = "okf-query-agent"
  }
}

# Cloud Spanner Database with Property Graph, Vector & Full-Text Indexes
resource "google_spanner_database" "okf_knowledge_graph" {
  instance            = google_spanner_instance.okf_knowledge_spanner.name
  name                = var.spanner_database_id
  deletion_protection = false
}

# Authorize Agent SA to query & update Cloud Spanner Database (Rule 10: Zero allUsers)
resource "google_spanner_database_iam_member" "agent_spanner_user" {
  instance = google_spanner_instance.okf_knowledge_spanner.name
  database = google_spanner_database.okf_knowledge_graph.name
  role     = "roles/spanner.databaseUser"
  member   = "serviceAccount:${google_service_account.extracter_agent_sa.email}"
}

# Separate Cloud Run Service for OKF Spanner Graph & Retrieval Workbench UI (Rule 6, 9, 10)
resource "google_cloud_run_v2_service" "okf_query_agent_web" {
  name                 = "okf-query-agent-web-${var.environment}"
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = true

  template {
    service_account = google_service_account.extracter_agent_sa.email
    timeout         = "600s"

    containers {
      image = var.query_web_image

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      env {
        name  = "GEMINI_LOCATION"
        value = "global"
      }
      env {
        name  = "GEMINI_MODEL"
        value = "gemini-3.8-flash"
      }
      env {
        name  = "SPANNER_INSTANCE_ID"
        value = google_spanner_instance.okf_knowledge_spanner.name
      }
      env {
        name  = "SPANNER_DATABASE_ID"
        value = google_spanner_database.okf_knowledge_graph.name
      }
      env {
        name  = "APP_MODULE"
        value = "query_agent.web_server:app"
      }

      liveness_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 10
        period_seconds        = 30
        timeout_seconds       = 5
        failure_threshold     = 3
      }
    }
  }
}
