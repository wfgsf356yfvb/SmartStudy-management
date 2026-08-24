"""Explicit, serializable tenant references for background jobs."""

from tenant_services.middleware.tenant_resolver import validate_subdomain


class TenantJobContextError(ValueError):
    """Raised when a background job does not carry a valid tenant reference."""


def make_tenant_job_ref(subdomain, job_id):
    return {
        "job_id": str(job_id),
        "subdomain": validate_subdomain(subdomain),
    }


def validate_tenant_job_ref(reference, expected_subdomain=None, expected_job_id=None):
    if not isinstance(reference, dict) or not reference.get("job_id"):
        raise TenantJobContextError("Missing tenant job context")
    try:
        subdomain = validate_subdomain(reference.get("subdomain"))
    except ValueError as exc:
        raise TenantJobContextError("Invalid tenant job context") from exc
    if expected_subdomain is not None and subdomain != validate_subdomain(expected_subdomain):
        raise TenantJobContextError("Inconsistent tenant job context")
    job_id = str(reference["job_id"])
    if expected_job_id is not None and job_id != str(expected_job_id):
        raise TenantJobContextError("Inconsistent tenant job context")
    return {"job_id": job_id, "subdomain": subdomain}


def resolve_tenant_job_ref(reference, control_lookup):
    """Validate a job reference against the control DB before tenant work."""
    validated = validate_tenant_job_ref(reference)
    record = control_lookup(validated["subdomain"])
    if not isinstance(record, dict):
        raise TenantJobContextError("Tenant does not exist")
    if str(record.get("subdomain", "")).lower() != validated["subdomain"]:
        raise TenantJobContextError("Tenant mapping mismatch")
    if (
        record.get("deleted")
        or record.get("disabled")
        or record.get("subscription_status") in {"deleted", "disabled", "inactive", "provisioning"}
    ):
        raise TenantJobContextError("Tenant is not active")
    return record
