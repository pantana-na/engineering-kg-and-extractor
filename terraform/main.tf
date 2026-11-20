# Terraform Infrastructure for Unified OKF Engineering Workbench v2 & Parameterized Pipeline Job
# Complies with SPEC-20261120-UNIFIED-WORKBENCH-V2, Rule 9 (Infrastructure Manager, FinOps Labels)
# & Rule 10 (Zero allUsers, Pattern 1B Direct Cloud Run Native IAP)

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

locals {
  default_max_instances = lower(var.environment) == "prod" ? 5 : 3
  shared_max_instances  = var.cloud_run_max_instances != null ? var.cloud_run_max_instances : local.default_max_instances

  workbench_service_account = var.extracter_web_service_account != "" ? var.extracter_web_service_account : (var.cloud_run_service_account != "" ? var.cloud_run_service_account : google_service_account.extracter_agent_sa.email)
  workbench_ingress         = var.extracter_web_ingress != "" ? var.extracter_web_ingress : var.cloud_run_ingress
  workbench_security_mode   = lower(var.extracter_web_security_mode != "" ? var.extracter_web_security_mode : var.cloud_run_security_mode)
  workbench_vpc_mode        = lower(var.extracter_web_vpc_mode != "" ? var.extracter_web_vpc_mode : var.cloud_run_vpc_mode)
  workbench_vpc_egress      = var.extracter_web_vpc_egress != "" ? var.extracter_web_vpc_egress : var.cloud_run_vpc_egress
  workbench_vpc_network     = var.extracter_web_vpc_network != "" ? var.extracter_web_vpc_network : var.cloud_run_vpc_network
  workbench_vpc_subnet      = var.extracter_web_vpc_subnet != "" ? var.extracter_web_vpc_subnet : var.cloud_run_vpc_subnet
  workbench_vpc_connector   = var.extracter_web_vpc_connector != "" ? var.extracter_web_vpc_connector : var.cloud_run_vpc_connector
  workbench_cpu             = var.extracter_web_cpu != "" ? var.extracter_web_cpu : var.cloud_run_cpu
  workbench_memory          = var.extracter_web_memory != "" ? var.extracter_web_memory : var.cloud_run_memory
  workbench_concurrency     = var.extracter_web_concurrency != null ? var.extracter_web_concurrency : var.cloud_run_concurrency
  workbench_timeout_seconds = var.extracter_web_timeout_seconds != null ? var.extracter_web_timeout_seconds : var.cloud_run_timeout_seconds
  workbench_min_instances   = var.extracter_web_min_instances != null ? var.extracter_web_min_instances : var.cloud_run_min_instances
  workbench_max_instances   = var.extracter_web_max_instances != null ? var.extracter_web_max_instances : local.shared_max_instances

  common_labels = {
    env         = lower(var.environment)
    service     = "okf-engineering-workbench"
    owner       = "platform-engineering"
    cost_center = var.cost_center
    managed_by  = "infrastructure-manager"
  }

  required_apis = toset([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "spanner.googleapis.com",
    "storage.googleapis.com",
    "dataplex.googleapis.com",
    "datalineage.googleapis.com",
    "iap.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "modelarmor.googleapis.com",
    "dlp.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudtrace.googleapis.com",
    "secretmanager.googleapis.com",
  ])
}

# Enable Required Google Cloud APIs (idempotent for brand-new GCP projects)
resource "google_project_service" "required_apis" {
  for_each           = var.enable_apis ? local.required_apis : toset([])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# Artifact Registry Repository for Unified Container Image
resource "google_artifact_registry_repository" "okf_workbench" {
  location      = var.region
  repository_id = var.artifact_registry_repo
  format        = "DOCKER"
  description   = "Unified container image for okf-engineering-workbench & okf-pipeline-job"
  labels        = local.common_labels

  depends_on = [google_project_service.required_apis]
}

# GCS Bucket for OKF Knowledge Bundles & Raw Documents
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

  labels     = local.common_labels
  depends_on = [google_project_service.required_apis]
}

# Dedicated Least-Privilege Runtime Service Account
resource "google_service_account" "extracter_agent_sa" {
  account_id   = "okf-workbench-${var.environment}"
  display_name = "OKF Unified Engineering Workbench SA (${var.environment})"
  depends_on   = [google_project_service.required_apis]
}

# Authorize Runtime SA on GCS Bucket (Rule 10: Zero allUsers)
resource "google_storage_bucket_iam_member" "agent_bucket_admin" {
  bucket = google_storage_bucket.okf_knowledge_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.extracter_agent_sa.email}"
}

# Authorize Runtime SA for Vertex AI Gemini & Embeddings
resource "google_project_iam_member" "runtime_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.extracter_agent_sa.email}"
}

# Authorize Spanner Service Agent for Native Spanner ML.PREDICT Embeddings
resource "google_project_iam_member" "spanner_sa_aiplatform_user" {
  project    = var.project_id
  role       = "roles/aiplatform.user"
  member     = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-spanner.iam.gserviceaccount.com"
  depends_on = [google_project_service.required_apis]
}

# Cloud Spanner Enterprise Instance (Property Graph, ANN Vector Index, Native ML.PREDICT & Lineage)
resource "google_spanner_instance" "okf_knowledge_spanner" {
  name             = "${var.spanner_instance_id}-${var.environment}"
  config           = "regional-${var.region}"
  display_name     = "OKF Graph (${var.environment})"
  processing_units = var.spanner_processing_units
  edition          = "ENTERPRISE"
  labels           = local.common_labels
  depends_on       = [google_project_service.required_apis]
}

resource "google_spanner_database" "okf_knowledge_graph" {
  instance            = google_spanner_instance.okf_knowledge_spanner.name
  name                = var.spanner_database_id
  deletion_protection = false
}

resource "google_spanner_database_iam_member" "agent_spanner_user" {
  instance = google_spanner_instance.okf_knowledge_spanner.name
  database = google_spanner_database.okf_knowledge_graph.name
  role     = "roles/spanner.databaseUser"
  member   = "serviceAccount:${google_service_account.extracter_agent_sa.email}"
}

# ==============================================================================
# Unified Cloud Run Service: `okf-engineering-workbench` (Extractor + Query UI)
# ==============================================================================
resource "google_cloud_run_v2_service" "okf_engineering_workbench" {
  provider             = google-beta
  name                 = "${var.unified_web_service_name}-${var.environment}"
  location             = var.region
  ingress              = local.workbench_ingress
  invoker_iam_disabled = local.workbench_security_mode == "unauthenticated"
  iap_enabled          = local.workbench_security_mode == "iap"
  labels               = local.common_labels

  template {
    service_account = local.workbench_service_account

    timeout                          = "${local.workbench_timeout_seconds}s"
    max_instance_request_concurrency = local.workbench_concurrency

    scaling {
      min_instance_count = local.workbench_min_instances
      max_instance_count = local.workbench_max_instances
    }

    dynamic "vpc_access" {
      for_each = local.workbench_vpc_mode == "none" ? [] : [1]
      content {
        egress    = local.workbench_vpc_egress
        connector = local.workbench_vpc_mode == "connector" ? local.workbench_vpc_connector : null

        dynamic "network_interfaces" {
          for_each = local.workbench_vpc_mode == "direct" ? [1] : []
          content {
            network    = local.workbench_vpc_network
            subnetwork = local.workbench_vpc_subnet
          }
        }
      }
    }

    containers {
      image = var.unified_web_image != "" ? var.unified_web_image : var.extracter_web_image

      resources {
        cpu_idle = false
        startup_cpu_boost = true
        limits = {
          cpu    = local.workbench_cpu
          memory = local.workbench_memory
        }
      }

      env {
        name  = "DEPLOYMENT_ENV"
        value = upper(var.environment)
      }
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
        value = var.gemini_model
      }
      env {
        name  = "EXTRACTER_DEFAULT_MODEL"
        value = var.extracter_default_model
      }
      env {
        name  = "QUERY_DEFAULT_MODEL"
        value = var.query_default_model
      }
      env {
        name  = "ALLOWED_GEMINI_MODELS"
        value = var.allowed_gemini_models
      }
      env {
        name  = "SPANNER_NATIVE_EMBEDDING_MODE"
        value = var.spanner_native_embedding_mode
      }
      env {
        name  = "SPANNER_EMBEDDING_LOCATION"
        value = var.region
      }
      env {
        name  = "DESTINATION_GCS_BUCKET"
        value = google_storage_bucket.okf_knowledge_bucket.name
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
        name  = "PIPELINE_JOB_NAME"
        value = google_cloud_run_v2_job.okf_pipeline_job.name
      }
      env {
        name  = "CLOUD_RUN_JOBS_EXECUTION_MODE"
        value = "cloud_run_job"
      }
      env {
        name  = "IAP_JWT_ENFORCEMENT"
        value = local.workbench_security_mode == "iap" ? "true" : "false"
      }
      env {
        name  = "APP_MODULE"
        value = "unified_web.server:app"
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

  depends_on = [google_project_service.required_apis]
}

# ==============================================================================
# Single Parameterized Cloud Run Job: `okf-pipeline-job`
# Supports `JOB_MODE=extract | sync | extract_and_sync` via container env overrides
# ==============================================================================
resource "google_cloud_run_v2_job" "okf_pipeline_job" {
  name     = "${var.pipeline_job_name}-${var.environment}"
  location = var.region
  labels   = local.common_labels

  template {
    task_count = 1
    template {
      service_account = local.workbench_service_account
      timeout         = "${var.pipeline_job_timeout_seconds}s"
      max_retries     = 1

      dynamic "vpc_access" {
        for_each = local.workbench_vpc_mode == "none" ? [] : [1]
        content {
          egress    = local.workbench_vpc_egress
          connector = local.workbench_vpc_mode == "connector" ? local.workbench_vpc_connector : null

          dynamic "network_interfaces" {
            for_each = local.workbench_vpc_mode == "direct" ? [1] : []
            content {
              network    = local.workbench_vpc_network
              subnetwork = local.workbench_vpc_subnet
            }
          }
        }
      }

      containers {
        image   = var.unified_web_image != "" ? var.unified_web_image : var.extracter_web_image
        command = ["python", "-m", "scripts.pipeline_job_runner"]

        resources {
          limits = {
            cpu    = local.workbench_cpu
            memory = local.workbench_memory
          }
        }

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
          name  = "USE_GCS_STORAGE"
          value = "true"
        }
        env {
          name  = "GEMINI_LOCATION"
          value = "global"
        }
        env {
          name  = "GEMINI_MODEL"
          value = var.extracter_default_model
        }
        env {
          name  = "SPANNER_NATIVE_EMBEDDING_MODE"
          value = var.spanner_native_embedding_mode
        }
        env {
          name  = "SPANNER_EMBEDDING_LOCATION"
          value = var.region
        }
        env {
          name  = "DESTINATION_GCS_BUCKET"
          value = google_storage_bucket.okf_knowledge_bucket.name
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
          name  = "PIPELINE_JOB_NAME"
          value = "${var.pipeline_job_name}-${var.environment}"
        }
      }
    }
  }

  depends_on = [google_project_service.required_apis]
}

# Scoped IAM: Allow Unified Workbench SA to trigger `okf-pipeline-job` executions
resource "google_cloud_run_v2_job_iam_member" "workbench_run_job" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.okf_pipeline_job.name
  role     = "roles/run.developer"
  member   = "serviceAccount:${local.workbench_service_account}"
}
