output "okf_bucket_name" {
  description = "Name of the GCS bucket hosting OKF knowledge bundles"
  value       = google_storage_bucket.okf_knowledge_bucket.name
}

output "okf_bucket_url" {
  description = "GCS URI for the knowledge bundles root"
  value       = "gs://${google_storage_bucket.okf_knowledge_bucket.name}"
}

output "service_account_email" {
  description = "Service account email running the agent"
  value       = google_service_account.extracter_agent_sa.email
}
