"""Externalized Cloud Build & Cloud Run Configuration Resolver for Both Web Apps.

Implements SPEC-20261104-GEMINI4-ARGON-AND-CLOUD-RUN-EXTERNALIZED-CONFIG:
  1. Gemini 4 Argon (`gemini-4-argon`) default model configuration.
  2. Externalized Cloud Build service account (`CLOUDBUILD_SERVICE_ACCOUNT` + per-env overrides).
  3. Externalized Cloud Run runtime service account (`CLOUD_RUN_SERVICE_ACCOUNT` + per-env / per-app overrides).
  4. Externalized Cloud Run networking (`all` | `internal-and-cloud-load-balancing` | `internal`).
  5. Externalized Cloud Run security (`iap` [IAM + Cloud Run Native IAP] | `iam` | `unauthenticated`).
  6. Externalized Cloud Run VPC egress (`direct` [Direct VPC Egress] | `connector` | `none`).

Supports both web applications (`EXTRACTER_WEB` and `QUERY_WEB`) across `NONPROD` and `PROD`
using deterministic 4-level precedence:
  `{ENV}_{APP}_{PARAM}` -> `{APP}_{PARAM}` -> `{ENV}_CLOUD_RUN_{PARAM}` -> `CLOUD_RUN_{PARAM}`
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from enum import Enum
from typing import Mapping, Optional

from pydantic import BaseModel, Field, model_validator


DEFAULT_GEMINI_MODEL = "gemini-4-argon"
DEFAULT_COMPUTE_SA_PLACEHOLDER = "000000000000-compute@developer.gserviceaccount.com"

VALID_APP_KEYS = ("EXTRACTER_WEB", "QUERY_WEB")
VALID_ENV_KEYS = ("NONPROD", "PROD")
VALID_CLOUD_RUN_CPUS = ("1", "2", "4", "6", "8")

DEFAULT_CLOUD_RUN_CPU = "4"
DEFAULT_CLOUD_RUN_MEMORY = "8Gi"
DEFAULT_CLOUD_RUN_CONCURRENCY = 30
DEFAULT_CLOUD_RUN_TIMEOUT_SECONDS = 3600
DEFAULT_NONPROD_MIN_INSTANCES = 0
DEFAULT_NONPROD_MAX_INSTANCES = 3
DEFAULT_PROD_MIN_INSTANCES = 0
DEFAULT_PROD_MAX_INSTANCES = 5

_MEMORY_QUANTITY_RE = re.compile(r"^(\d+)(Mi|Gi)$")
_CPU_MIN_MEMORY_MIB: dict[str, int] = {
    "1": 512,
    "2": 512,
    "4": 2048,
    "6": 4096,
    "8": 4096,
}


def parse_memory_to_mib(raw_memory: str) -> tuple[str, int]:
    """Validate a Cloud Run Kubernetes memory string (Mi/Gi) and return `(canonical_str, mib)`."""
    cleaned = raw_memory.strip()
    match = _MEMORY_QUANTITY_RE.match(cleaned)
    if not match:
        raise ValueError(
            f"Invalid Cloud Run memory '{raw_memory}'. Expected integer Mi or Gi (e.g., '512Mi', '2Gi', '8Gi', '16Gi')."
        )
    amount = int(match.group(1))
    unit = match.group(2)
    mib = amount * 1024 if unit == "Gi" else amount
    if mib < 512 or mib > 32768:
        raise ValueError(
            f"Cloud Run memory '{cleaned}' ({mib} MiB) out of supported bounds (512Mi .. 32Gi)."
        )
    return cleaned, mib


def parse_timeout_seconds(raw_timeout: str | int) -> int:
    """Parse timeout seconds from integer or `<N>s` string and validate Cloud Run bounds (1..3600)."""
    if isinstance(raw_timeout, int):
        val = raw_timeout
    else:
        cleaned = raw_timeout.strip().lower()
        if cleaned.endswith("s"):
            cleaned = cleaned[:-1].strip()
        if not cleaned.isdigit():
            raise ValueError(
                f"Invalid Cloud Run timeout '{raw_timeout}'. Expected integer seconds 1..3600 (e.g., '900' or '900s')."
            )
        val = int(cleaned)
    if val < 1 or val > 3600:
        raise ValueError(f"Cloud Run timeout {val}s out of supported bounds (1..3600).")
    return val


class CloudRunIngressMode(str, Enum):
    """Canonical Cloud Run ingress modes."""

    ALL = "all"
    INTERNAL_AND_CLOUD_LOAD_BALANCING = "internal-and-cloud-load-balancing"
    INTERNAL = "internal"


class CloudRunSecurityMode(str, Enum):
    """Canonical Cloud Run security & authentication modes."""

    IAP = "iap"  # Require authentication (IAM + Cloud Run Native IAP)
    IAM = "iam"  # Require authentication (IAM only, no IAP)
    UNAUTHENTICATED = "unauthenticated"  # Org-Policy-safe invoker-iam-disabled (zero allUsers)


class CloudRunVpcMode(str, Enum):
    """Canonical Cloud Run VPC connectivity modes."""

    DIRECT = "direct"  # Direct VPC egress (--network + --subnet)
    CONNECTOR = "connector"  # Serverless VPC Access Connector (--vpc-connector)
    NONE = "none"  # No VPC egress


class CloudRunVpcEgress(str, Enum):
    """Canonical Cloud Run VPC egress traffic routing settings."""

    ALL_TRAFFIC = "all-traffic"
    PRIVATE_RANGES_ONLY = "private-ranges-only"


_INGRESS_ALIASES: dict[str, CloudRunIngressMode] = {
    "all": CloudRunIngressMode.ALL,
    "ingress_traffic_all": CloudRunIngressMode.ALL,
    "internal-and-cloud-load-balancing": CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING,
    "internal_and_cloud_load_balancing": CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING,
    "internal + external loadbalancer": CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING,
    "internal + external load balancer": CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING,
    "inernal + external loadbalancer": CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING,
    "internal+external loadbalancer": CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING,
    "internal-load-balancer": CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING,
    "ingress_traffic_internal_load_balancer": CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING,
    "internal": CloudRunIngressMode.INTERNAL,
    "internal-only": CloudRunIngressMode.INTERNAL,
    "ingress_traffic_internal_only": CloudRunIngressMode.INTERNAL,
}

_SECURITY_ALIASES: dict[str, CloudRunSecurityMode] = {
    "iap": CloudRunSecurityMode.IAP,
    "iam+iap": CloudRunSecurityMode.IAP,
    "iam + iap": CloudRunSecurityMode.IAP,
    "require authentication (iam + iap)": CloudRunSecurityMode.IAP,
    "require-authentication-iam-iap": CloudRunSecurityMode.IAP,
    "native-iap": CloudRunSecurityMode.IAP,
    "iam": CloudRunSecurityMode.IAM,
    "require authentication": CloudRunSecurityMode.IAM,
    "require authentication (iam)": CloudRunSecurityMode.IAM,
    "require-authentication": CloudRunSecurityMode.IAM,
    "unauthenticated": CloudRunSecurityMode.UNAUTHENTICATED,
    "public": CloudRunSecurityMode.UNAUTHENTICATED,
    "invoker-iam-disabled": CloudRunSecurityMode.UNAUTHENTICATED,
    "no-invoker-iam-check": CloudRunSecurityMode.UNAUTHENTICATED,
    "allow-unauthenticated": CloudRunSecurityMode.UNAUTHENTICATED,
}

_VPC_MODE_ALIASES: dict[str, CloudRunVpcMode] = {
    "direct": CloudRunVpcMode.DIRECT,
    "direct-vpc": CloudRunVpcMode.DIRECT,
    "direct_vpc": CloudRunVpcMode.DIRECT,
    "sending all traffic to the vpc directly": CloudRunVpcMode.DIRECT,
    "send all traffic to the vpc directly": CloudRunVpcMode.DIRECT,
    "connector": CloudRunVpcMode.CONNECTOR,
    "vpc-connector": CloudRunVpcMode.CONNECTOR,
    "vpc_connector": CloudRunVpcMode.CONNECTOR,
    "serverless-vpc-connector": CloudRunVpcMode.CONNECTOR,
    "serverless vpc access connector": CloudRunVpcMode.CONNECTOR,
    "serverless vpc access connectors": CloudRunVpcMode.CONNECTOR,
    "none": CloudRunVpcMode.NONE,
    "disabled": CloudRunVpcMode.NONE,
    "off": CloudRunVpcMode.NONE,
}

_VPC_EGRESS_ALIASES: dict[str, CloudRunVpcEgress] = {
    "all-traffic": CloudRunVpcEgress.ALL_TRAFFIC,
    "all_traffic": CloudRunVpcEgress.ALL_TRAFFIC,
    "all": CloudRunVpcEgress.ALL_TRAFFIC,
    "private-ranges-only": CloudRunVpcEgress.PRIVATE_RANGES_ONLY,
    "private_ranges_only": CloudRunVpcEgress.PRIVATE_RANGES_ONLY,
    "private": CloudRunVpcEgress.PRIVATE_RANGES_ONLY,
}

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:@/-]+$")


def _normalize_whitespace_key(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip().lower())


def parse_ingress_mode(raw: str) -> CloudRunIngressMode:
    """Normalize human-readable or CLI ingress string into CloudRunIngressMode."""
    key = _normalize_whitespace_key(raw)
    if key in _INGRESS_ALIASES:
        return _INGRESS_ALIASES[key]
    raise ValueError(
        f"Invalid Cloud Run ingress configuration '{raw}'. "
        f"Expected 'all', 'internal-and-cloud-load-balancing' (or 'internal + external loadbalancer'), or 'internal'."
    )


def parse_security_mode(raw: str) -> CloudRunSecurityMode:
    """Normalize human-readable or CLI security string into CloudRunSecurityMode."""
    key = _normalize_whitespace_key(raw)
    if key in _SECURITY_ALIASES:
        return _SECURITY_ALIASES[key]
    raise ValueError(
        f"Invalid Cloud Run security configuration '{raw}'. "
        f"Expected 'iap' ('require authentication (IAM + IAP)'), 'iam', or 'unauthenticated'."
    )


def parse_vpc_mode(raw: str) -> CloudRunVpcMode:
    """Normalize human-readable or CLI VPC mode string into CloudRunVpcMode."""
    key = _normalize_whitespace_key(raw)
    if key in _VPC_MODE_ALIASES:
        return _VPC_MODE_ALIASES[key]
    raise ValueError(
        f"Invalid Cloud Run VPC mode '{raw}'. "
        f"Expected 'direct' ('sending all traffic to the VPC directly'), 'connector', or 'none'."
    )


def parse_vpc_egress(raw: str) -> CloudRunVpcEgress:
    """Normalize VPC egress routing string into CloudRunVpcEgress."""
    key = _normalize_whitespace_key(raw)
    if key in _VPC_EGRESS_ALIASES:
        return _VPC_EGRESS_ALIASES[key]
    raise ValueError(
        f"Invalid Cloud Run VPC egress setting '{raw}'. "
        f"Expected 'all-traffic' or 'private-ranges-only'."
    )


def normalize_cloudbuild_service_account(project_id: str, raw_sa: str) -> str:
    """Normalize a Cloud Build service account email or resource URI into canonical URI form.

    Idempotent: passing `projects/<proj>/serviceAccounts/<email>` returns it unchanged.
    """
    cleaned_project = project_id.strip()
    cleaned_sa = raw_sa.strip()
    if not cleaned_project:
        raise ValueError("project_id must be non-empty when normalizing Cloud Build service account.")
    if not cleaned_sa:
        raise ValueError("Cloud Build service account must be non-empty.")
    if not _SAFE_TOKEN_RE.match(cleaned_sa) or not _SAFE_TOKEN_RE.match(cleaned_project):
        raise ValueError(f"Unsafe characters in project_id or service account: '{cleaned_sa}'.")

    prefix_match = re.match(r"^projects/([^/]+)/serviceAccounts/(.+)$", cleaned_sa)
    if prefix_match:
        sa_proj, sa_email = prefix_match.group(1), prefix_match.group(2)
        if "@" not in sa_email:
            raise ValueError(f"Service account URI must contain a valid email: '{cleaned_sa}'.")
        return f"projects/{sa_proj}/serviceAccounts/{sa_email}"

    if "@" not in cleaned_sa:
        raise ValueError(
            f"Cloud Build service account '{cleaned_sa}' must be a valid email or projects/<project>/serviceAccounts/<email>."
        )
    return f"projects/{cleaned_project}/serviceAccounts/{cleaned_sa}"


def normalize_cloud_run_service_account(raw_sa: str) -> str:
    """Normalize a Cloud Run runtime service account email or resource URI into canonical email form.

    `gcloud run deploy --service-account` and Terraform `google_cloud_run_v2_service.template.service_account`
    accept `<email>`. Passing `projects/<proj>/serviceAccounts/<email>` extracts `<email>` idempotently.
    """
    cleaned_sa = raw_sa.strip()
    if not cleaned_sa:
        raise ValueError("Cloud Run service account must be non-empty.")
    if not _SAFE_TOKEN_RE.match(cleaned_sa):
        raise ValueError(f"Unsafe characters in Cloud Run service account: '{cleaned_sa}'.")

    prefix_match = re.match(r"^projects/([^/]+)/serviceAccounts/(.+)$", cleaned_sa)
    email = prefix_match.group(2) if prefix_match else cleaned_sa
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError(
            f"Cloud Run service account '{cleaned_sa}' must be a valid email or projects/<project>/serviceAccounts/<email>."
        )
    return email


def _first_non_empty(env_map: Mapping[str, str], keys: list[str], default: str = "") -> str:
    for key in keys:
        val = env_map.get(key)
        if val is not None and val.strip() != "":
            return val.strip()
    return default


class WebAppCloudRunConfig(BaseModel):
    """Resolved Cloud Build & Cloud Run configuration for a specific web application."""

    app_key: str
    environment: str
    project_id: str
    service_name: str
    gemini_model: str = Field(default=DEFAULT_GEMINI_MODEL)
    cloudbuild_service_account: str
    service_account: str = Field(default=DEFAULT_COMPUTE_SA_PLACEHOLDER)
    ingress: CloudRunIngressMode = Field(default=CloudRunIngressMode.ALL)
    security_mode: CloudRunSecurityMode = Field(default=CloudRunSecurityMode.IAP)
    vpc_mode: CloudRunVpcMode = Field(default=CloudRunVpcMode.DIRECT)
    vpc_egress: CloudRunVpcEgress = Field(default=CloudRunVpcEgress.ALL_TRAFFIC)
    vpc_network: Optional[str] = None
    vpc_subnet: Optional[str] = None
    vpc_connector: Optional[str] = None
    cpu: str = Field(default=DEFAULT_CLOUD_RUN_CPU)
    memory: str = Field(default=DEFAULT_CLOUD_RUN_MEMORY)
    concurrency: int = Field(default=DEFAULT_CLOUD_RUN_CONCURRENCY)
    timeout_seconds: int = Field(default=DEFAULT_CLOUD_RUN_TIMEOUT_SECONDS)
    min_instances: int = Field(default=DEFAULT_NONPROD_MIN_INSTANCES)
    max_instances: int = Field(default=DEFAULT_NONPROD_MAX_INSTANCES)

    @model_validator(mode="after")
    def _validate_vpc_and_tokens(self) -> "WebAppCloudRunConfig":
        if self.app_key not in VALID_APP_KEYS:
            raise ValueError(f"app_key must be one of {VALID_APP_KEYS}, got '{self.app_key}'.")
        if self.environment not in VALID_ENV_KEYS:
            raise ValueError(f"environment must be one of {VALID_ENV_KEYS}, got '{self.environment}'.")

        # Normalize Cloud Build & Cloud Run runtime service accounts
        self.cloudbuild_service_account = normalize_cloudbuild_service_account(
            self.project_id, self.cloudbuild_service_account
        )
        self.service_account = normalize_cloud_run_service_account(self.service_account)

        if self.vpc_mode == CloudRunVpcMode.DIRECT:
            if not self.vpc_network or not self.vpc_network.strip():
                raise ValueError(
                    f"[{self.environment}:{self.app_key}] VPC_MODE='direct' requires VPC_NETWORK to be set in .env."
                )
            if not self.vpc_subnet or not self.vpc_subnet.strip():
                raise ValueError(
                    f"[{self.environment}:{self.app_key}] VPC_MODE='direct' requires VPC_SUBNET to be set in .env."
                )
            if not _SAFE_TOKEN_RE.match(self.vpc_network) or not _SAFE_TOKEN_RE.match(self.vpc_subnet):
                raise ValueError("Unsafe characters in VPC_NETWORK or VPC_SUBNET.")
        elif self.vpc_mode == CloudRunVpcMode.CONNECTOR:
            if not self.vpc_connector or not self.vpc_connector.strip():
                raise ValueError(
                    f"[{self.environment}:{self.app_key}] VPC_MODE='connector' requires VPC_CONNECTOR to be set in .env."
                )
            if not _SAFE_TOKEN_RE.match(self.vpc_connector):
                raise ValueError("Unsafe characters in VPC_CONNECTOR.")

        # Validate CPU, memory, concurrency, timeout, and min/max instance scaling
        cleaned_cpu = str(self.cpu).strip()
        if cleaned_cpu not in VALID_CLOUD_RUN_CPUS:
            raise ValueError(
                f"Invalid Cloud Run CPU '{self.cpu}'. Expected one of {VALID_CLOUD_RUN_CPUS}."
            )
        self.cpu = cleaned_cpu

        canonical_mem, mem_mib = parse_memory_to_mib(self.memory)
        min_required_mib = _CPU_MIN_MEMORY_MIB[self.cpu]
        if mem_mib < min_required_mib:
            raise ValueError(
                f"[{self.environment}:{self.app_key}] Cloud Run CPU={self.cpu} requires at least "
                f"{min_required_mib}Mi memory, got '{canonical_mem}'."
            )
        self.memory = canonical_mem

        if self.concurrency < 1 or self.concurrency > 1000:
            raise ValueError(
                f"Cloud Run concurrency {self.concurrency} out of supported bounds (1..1000)."
            )

        self.timeout_seconds = parse_timeout_seconds(self.timeout_seconds)

        if self.min_instances < 0:
            raise ValueError(f"Cloud Run min_instances must be >= 0, got {self.min_instances}.")
        if self.max_instances < 1:
            raise ValueError(f"Cloud Run max_instances must be >= 1, got {self.max_instances}.")
        if self.min_instances > self.max_instances:
            raise ValueError(
                f"[{self.environment}:{self.app_key}] min_instances ({self.min_instances}) "
                f"cannot exceed max_instances ({self.max_instances})."
            )

        return self

    def to_gcloud_deploy_flags(self) -> list[str]:
        """Build deterministic, Org-Policy-compliant `gcloud run deploy` flags."""
        flags: list[str] = [
            f"--build-service-account={self.cloudbuild_service_account}",
            f"--service-account={self.service_account}",
            f"--ingress={self.ingress.value}",
            f"--cpu={self.cpu}",
            f"--memory={self.memory}",
            f"--concurrency={self.concurrency}",
            f"--timeout={self.timeout_seconds}",
            f"--min-instances={self.min_instances}",
            f"--max-instances={self.max_instances}",
        ]

        # Security flags (strictly zero `--allow-unauthenticated` / zero `allUsers`)
        if self.security_mode == CloudRunSecurityMode.IAP:
            flags.extend(["--no-allow-unauthenticated", "--invoker-iam-check", "--iap"])
        elif self.security_mode == CloudRunSecurityMode.IAM:
            flags.extend(["--no-allow-unauthenticated", "--invoker-iam-check", "--no-iap"])
        elif self.security_mode == CloudRunSecurityMode.UNAUTHENTICATED:
            flags.extend(["--no-invoker-iam-check", "--no-iap"])

        # Mutex-safe VPC egress flags
        if self.vpc_mode == CloudRunVpcMode.DIRECT:
            flags.extend(
                [
                    f"--network={self.vpc_network}",
                    f"--subnet={self.vpc_subnet}",
                    f"--vpc-egress={self.vpc_egress.value}",
                ]
            )
        elif self.vpc_mode == CloudRunVpcMode.CONNECTOR:
            flags.extend(
                [
                    f"--vpc-connector={self.vpc_connector}",
                    f"--vpc-egress={self.vpc_egress.value}",
                ]
            )
        elif self.vpc_mode == CloudRunVpcMode.NONE:
            flags.extend(["--clear-vpc-connector", "--clear-network"])

        return flags

    def to_terraform_attributes(self) -> dict[str, object]:
        """Map resolved configuration to Terraform `google_cloud_run_v2_service` attributes."""
        tf_ingress_map = {
            CloudRunIngressMode.ALL: "INGRESS_TRAFFIC_ALL",
            CloudRunIngressMode.INTERNAL_AND_CLOUD_LOAD_BALANCING: "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER",
            CloudRunIngressMode.INTERNAL: "INGRESS_TRAFFIC_INTERNAL_ONLY",
        }
        tf_egress_map = {
            CloudRunVpcEgress.ALL_TRAFFIC: "ALL_TRAFFIC",
            CloudRunVpcEgress.PRIVATE_RANGES_ONLY: "PRIVATE_RANGES_ONLY",
        }
        return {
            "service_account": self.service_account,
            "ingress": tf_ingress_map[self.ingress],
            "invoker_iam_disabled": self.security_mode == CloudRunSecurityMode.UNAUTHENTICATED,
            "iap_enabled": self.security_mode == CloudRunSecurityMode.IAP,
            "vpc_mode": self.vpc_mode.value,
            "vpc_egress": tf_egress_map[self.vpc_egress],
            "vpc_network": self.vpc_network if self.vpc_mode == CloudRunVpcMode.DIRECT else None,
            "vpc_subnet": self.vpc_subnet if self.vpc_mode == CloudRunVpcMode.DIRECT else None,
            "vpc_connector": self.vpc_connector if self.vpc_mode == CloudRunVpcMode.CONNECTOR else None,
            "cpu": self.cpu,
            "memory": self.memory,
            "concurrency": self.concurrency,
            "timeout": f"{self.timeout_seconds}s",
            "min_instances": self.min_instances,
            "max_instances": self.max_instances,
        }

    def to_posture_summary(self) -> dict[str, str]:
        """Return non-sensitive runtime posture summary for `/api/status`."""
        return {
            "ingress": self.ingress.value,
            "security_mode": self.security_mode.value,
            "vpc_mode": self.vpc_mode.value,
            "vpc_egress": self.vpc_egress.value,
        }


def resolve_webapp_cloud_run_config(
    app_key: str,
    environment: str = "NONPROD",
    env_vars: Optional[Mapping[str, str]] = None,
) -> WebAppCloudRunConfig:
    """Resolve `WebAppCloudRunConfig` from environment variables using 4-level precedence."""
    source = env_vars if env_vars is not None else os.environ
    norm_app = app_key.strip().upper()
    norm_env = environment.strip().upper()
    if norm_env in ("DEV", "DEVELOPMENT"):
        norm_env = "NONPROD"
    elif norm_env in ("PRODUCTION", "RELEASE"):
        norm_env = "PROD"

    project_id = _first_non_empty(
        source,
        [f"{norm_env}_PROJECT_ID", "GOOGLE_CLOUD_PROJECT"],
        default="your-gcp-project-id",
    )
    gemini_model = _first_non_empty(
        source,
        [f"{norm_env}_GEMINI_MODEL", "GEMINI_MODEL"],
        default=DEFAULT_GEMINI_MODEL,
    )

    if norm_app == "EXTRACTER_WEB":
        default_svc = "extracter-agent-web" if norm_env == "NONPROD" else "extracter-agent-web-prod"
        service_name = _first_non_empty(
            source,
            [
                f"{norm_env}_EXTRACTER_WEB_SERVICE_NAME",
                "CLOUD_RUN_WEB_SERVICE" if norm_env == "NONPROD" else "PROD_CLOUD_RUN_WEB_SERVICE",
                "CLOUD_RUN_WEB_SERVICE",
            ],
            default=default_svc,
        )
    elif norm_app == "QUERY_WEB":
        default_svc = "okf-query-agent-web" if norm_env == "NONPROD" else "okf-query-agent-web-prod"
        service_name = _first_non_empty(
            source,
            [
                f"{norm_env}_QUERY_WEB_SERVICE_NAME",
                "QUERY_WEB_SERVICE_NAME" if norm_env == "NONPROD" else "PROD_QUERY_WEB_SERVICE_NAME",
                "QUERY_WEB_SERVICE_NAME",
            ],
            default=default_svc,
        )
    else:
        raise ValueError(f"Unsupported app_key '{app_key}'. Expected one of {VALID_APP_KEYS}.")

    def _resolve_param(param: str, default: str = "", extra_env_keys: Optional[list[str]] = None) -> str:
        chain = [
            f"{norm_env}_{norm_app}_{param}",
            f"{norm_app}_{param}",
            f"{norm_env}_CLOUD_RUN_{param}",
        ]
        if extra_env_keys:
            chain.extend(extra_env_keys)
        chain.append(f"CLOUD_RUN_{param}")
        return _first_non_empty(source, chain, default=default)

    proj_num = _first_non_empty(source, ["GOOGLE_CLOUD_PROJECT_NUMBER"], default="")
    default_compute_sa = (
        f"{proj_num}-compute@developer.gserviceaccount.com"
        if proj_num.isdigit()
        else DEFAULT_COMPUTE_SA_PLACEHOLDER
    )

    raw_cb_sa = _first_non_empty(
        source,
        [
            f"{norm_env}_CLOUDBUILD_SERVICE_ACCOUNT",
            "CLOUDBUILD_SERVICE_ACCOUNT",
        ],
        default=default_compute_sa,
    )
    raw_runtime_sa = _resolve_param("SERVICE_ACCOUNT", default=default_compute_sa)

    ingress = parse_ingress_mode(_resolve_param("INGRESS", default="all"))
    security_mode = parse_security_mode(_resolve_param("SECURITY_MODE", default="iap"))
    vpc_mode = parse_vpc_mode(_resolve_param("VPC_MODE", default="direct"))
    vpc_egress = parse_vpc_egress(_resolve_param("VPC_EGRESS", default="all-traffic"))
    vpc_network = _resolve_param("VPC_NETWORK", default="default") or None
    vpc_subnet = _resolve_param("VPC_SUBNET", default="default") or None
    vpc_connector = _resolve_param("VPC_CONNECTOR", default="") or None

    raw_cpu = _resolve_param("CPU", default=DEFAULT_CLOUD_RUN_CPU)
    raw_memory = _resolve_param("MEMORY", default=DEFAULT_CLOUD_RUN_MEMORY)
    raw_concurrency = _resolve_param("CONCURRENCY", default=str(DEFAULT_CLOUD_RUN_CONCURRENCY))
    if not raw_concurrency.isdigit():
        raise ValueError(
            f"Invalid Cloud Run concurrency '{raw_concurrency}'. Expected positive integer 1..1000."
        )
    raw_timeout = parse_timeout_seconds(
        _resolve_param("TIMEOUT", default=str(DEFAULT_CLOUD_RUN_TIMEOUT_SECONDS))
    )

    default_min = (
        DEFAULT_PROD_MIN_INSTANCES if norm_env == "PROD" else DEFAULT_NONPROD_MIN_INSTANCES
    )
    default_max = (
        DEFAULT_PROD_MAX_INSTANCES if norm_env == "PROD" else DEFAULT_NONPROD_MAX_INSTANCES
    )
    raw_min = _resolve_param(
        "MIN_INSTANCES",
        default=str(default_min),
        extra_env_keys=[f"{norm_env}_MIN_INSTANCES"],
    )
    raw_max = _resolve_param(
        "MAX_INSTANCES",
        default=str(default_max),
        extra_env_keys=[f"{norm_env}_MAX_INSTANCES"],
    )
    try:
        min_instances = int(raw_min)
    except ValueError as exc:
        raise ValueError(f"Invalid Cloud Run MIN_INSTANCES '{raw_min}'. Expected integer >= 0.") from exc
    try:
        max_instances = int(raw_max)
    except ValueError as exc:
        raise ValueError(f"Invalid Cloud Run MAX_INSTANCES '{raw_max}'. Expected integer >= 1.") from exc

    return WebAppCloudRunConfig(
        app_key=norm_app,
        environment=norm_env,
        project_id=project_id,
        service_name=service_name,
        gemini_model=gemini_model,
        cloudbuild_service_account=raw_cb_sa,
        service_account=raw_runtime_sa,
        ingress=ingress,
        security_mode=security_mode,
        vpc_mode=vpc_mode,
        vpc_egress=vpc_egress,
        vpc_network=vpc_network,
        vpc_subnet=vpc_subnet,
        vpc_connector=vpc_connector,
        cpu=raw_cpu,
        memory=raw_memory,
        concurrency=int(raw_concurrency),
        timeout_seconds=raw_timeout,
        min_instances=min_instances,
        max_instances=max_instances,
    )


def get_safe_cloud_run_posture(
    app_key: str,
    environment: Optional[str] = None,
    env_vars: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """Return non-sensitive Cloud Run networking/security/VPC posture summary."""
    source = env_vars if env_vars is not None else os.environ
    resolved_env = environment or source.get("DEPLOYMENT_ENV") or "NONPROD"
    try:
        return resolve_webapp_cloud_run_config(
            app_key=app_key, environment=resolved_env, env_vars=source
        ).to_posture_summary()
    except ValueError:
        return {
            "ingress": "all",
            "security_mode": "iap",
            "vpc_mode": "direct",
            "vpc_egress": "all-traffic",
        }


_REASONING_ENGINE_RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "PORT",
        "K_SERVICE",
        "K_REVISION",
        "K_CONFIGURATION",
    }
)

_CLOUD_RUN_INFRA_PREFIXES: tuple[str, ...] = (
    "CLOUD_RUN_",
    "CLOUDBUILD_",
    "EXTRACTER_WEB_",
    "QUERY_WEB_",
    "NONPROD_CLOUD_RUN_",
    "NONPROD_CLOUDBUILD_",
    "NONPROD_EXTRACTER_WEB_",
    "NONPROD_QUERY_WEB_",
    "NONPROD_MIN_INSTANCES",
    "NONPROD_MAX_INSTANCES",
    "PROD_CLOUD_RUN_",
    "PROD_CLOUDBUILD_",
    "PROD_EXTRACTER_WEB_",
    "PROD_QUERY_WEB_",
    "PROD_MIN_INSTANCES",
    "PROD_MAX_INSTANCES",
)

MAX_REASONING_ENGINE_ENV_VARS = 100


def build_agent_runtime_env(
    raw_env: Mapping[str, Optional[str]],
    environment: str = "NONPROD",
) -> dict[str, str]:
    """Filter a unified `.env` mapping into a Vertex AI Reasoning Engine-compliant env dict.

    Enforces Vertex AI `ReasoningEngineSpec.DeploymentSpec.env` constraints:
    1. Every value must be a non-empty string (`Required field is not set` otherwise).
    2. Total environment variables must not exceed 100 (`MAX_REASONING_ENGINE_ENV_VARS`).
    3. Excludes reserved Vertex AI runtime keys, Cloud Run/Build-only keys, and inactive-tier keys.
    """
    norm_env = environment.strip().upper()
    if norm_env in ("DEV", "DEVELOPMENT"):
        norm_env = "NONPROD"
    elif norm_env in ("PRODUCTION", "RELEASE"):
        norm_env = "PROD"

    inactive_prefix = "PROD_" if norm_env == "NONPROD" else "NONPROD_"
    filtered: dict[str, str] = {"DEPLOYMENT_ENV": norm_env}

    for key, raw_val in raw_env.items():
        clean_key = (key or "").strip()
        if not clean_key or raw_val is None:
            continue
        clean_val = str(raw_val).strip()
        if not clean_val:
            continue
        if clean_key in _REASONING_ENGINE_RESERVED_KEYS:
            continue
        if clean_key.startswith(inactive_prefix):
            continue
        if clean_key.startswith(_CLOUD_RUN_INFRA_PREFIXES):
            continue
        filtered[clean_key] = clean_val

    # Force ephemeral writable bundle dir inside Agent Runtime container if local relative path is configured
    if filtered.get("OUTPUT_BUNDLE_DIR", "").startswith("build/"):
        filtered["OUTPUT_BUNDLE_DIR"] = "/tmp/okf_bundle"

    if len(filtered) > MAX_REASONING_ENGINE_ENV_VARS:
        raise ValueError(
            f"Scoped Agent Runtime env has {len(filtered)} variables, exceeding Vertex AI limit of {MAX_REASONING_ENGINE_ENV_VARS}."
        )
    return filtered


def render_agent_runtime_env(
    dotenv_path: str | os.PathLike[str] = ".env",
    environment: str = "NONPROD",
) -> str:
    """Read `dotenv_path` and render a clean `KEY=VALUE` file for `adk deploy agent_engine`."""
    from dotenv import dotenv_values

    raw_map = dotenv_values(dotenv_path)
    scoped = build_agent_runtime_env(raw_map, environment=environment)
    lines = [f"{k}={v}" for k, v in scoped.items()]
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> None:
    """CLI helper invoked by deployment scripts or operators to inspect resolved flags."""
    parser = argparse.ArgumentParser(description="Resolve Cloud Run, Cloud Build & Agent Runtime config from .env")
    parser.add_argument("--app", choices=VALID_APP_KEYS, required=False, default="EXTRACTER_WEB")
    parser.add_argument("--env", default="NONPROD")
    parser.add_argument("--dotenv-file", default=".env")
    parser.add_argument(
        "--format",
        choices=("json", "gcloud-flags", "shell", "agent-env"),
        default="json",
    )
    args = parser.parse_args()

    if args.format == "agent-env":
        print(
            render_agent_runtime_env(dotenv_path=args.dotenv_file, environment=args.env),
            end="",
        )
        return

    cfg = resolve_webapp_cloud_run_config(app_key=args.app, environment=args.env)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "config": cfg.model_dump(mode="json"),
                    "gcloud_flags": cfg.to_gcloud_deploy_flags(),
                    "terraform": cfg.to_terraform_attributes(),
                },
                indent=2,
            )
        )
    elif args.format == "gcloud-flags":
        print(" ".join(shlex.quote(flag) for flag in cfg.to_gcloud_deploy_flags()))
    elif args.format == "shell":
        flags_quoted = " ".join(shlex.quote(f) for f in cfg.to_gcloud_deploy_flags())
        print(f"RESOLVED_SERVICE_NAME={shlex.quote(cfg.service_name)}")
        print(f"RESOLVED_GEMINI_MODEL={shlex.quote(cfg.gemini_model)}")
        print(f"RESOLVED_CLOUDBUILD_SA={shlex.quote(cfg.cloudbuild_service_account)}")
        print(f"RESOLVED_RUNTIME_SA={shlex.quote(cfg.service_account)}")
        print(f"RESOLVED_SECURITY_MODE={shlex.quote(cfg.security_mode.value)}")
        print(f"RESOLVED_INGRESS={shlex.quote(cfg.ingress.value)}")
        print(f"RESOLVED_VPC_MODE={shlex.quote(cfg.vpc_mode.value)}")
        print(f"RESOLVED_CPU={shlex.quote(cfg.cpu)}")
        print(f"RESOLVED_MEMORY={shlex.quote(cfg.memory)}")
        print(f"RESOLVED_CONCURRENCY={shlex.quote(str(cfg.concurrency))}")
        print(f"RESOLVED_TIMEOUT={shlex.quote(str(cfg.timeout_seconds))}")
        print(f"RESOLVED_MIN_INSTANCES={shlex.quote(str(cfg.min_instances))}")
        print(f"RESOLVED_MAX_INSTANCES={shlex.quote(str(cfg.max_instances))}")
        print(f"RESOLVED_GCLOUD_FLAGS=({flags_quoted})")


if __name__ == "__main__":
    main()

