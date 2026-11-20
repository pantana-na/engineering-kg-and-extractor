output "okf_bucket_name" {
  description = "Name of the GCS bucket hosting OKF knowledge bundles"
  value       = google_storage_bucket.okf_knowledge_bucket.name
}

output "okf_bucket_url" {
  description = "GCS URI for the knowledge bundles root"
  value       = "gs://${google_storage_bucket.okf_knowledge_bucket.name}"
}

output "service_account_email" {
  description = "Default Terraform-managed service account email"
  value       = google_service_account.extracter_agent_sa.email
}

output "workbench_service_account" {
  description = "Resolved runtime service account for okf-engineering-workbench & okf-pipeline-job"
  value       = local.workbench_service_account
}

output "cloudbuild_service_account" {
  description = "Configured Cloud Build service account"
  value       = var.cloudbuild_service_account
}

output "okf_engineering_workbench_uri" {
  description = "Cloud Run URI for Unified OKF Engineering Workbench v2"
  value       = google_cloud_run_v2_service.okf_engineering_workbench.uri
}

output "okf_pipeline_job_name" {
  description = "Cloud Run Job resource name for parameterized batch extraction & Spanner sync"
  value       = google_cloud_run_v2_job.okf_pipeline_job.name
}
