"""Postgres-backed job queue (D10): no broker. Tests call run_pending() in-process.

See docs/adr/0001-job-queue-and-tenancy.md. Payloads carry identifiers only, and enqueue() enforces it.
Until ticket 02 the table is global; from then on jobs carry a company id under row-level security.
"""

import logging
import uuid

from django.db import transaction
from django.utils import timezone

from .models import Job

logger = logging.getLogger(__name__)

HANDLERS = {}

# Longest string accepted in a payload: enough for an id or reference number, too short for content.
MAX_STRING_LENGTH = 40


def register(name):
    def decorator(func):
        HANDLERS[name] = func
        return func

    return decorator


class JobPayloadError(ValueError):
    pass


def _identifier(key, value):
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str) and len(value) <= MAX_STRING_LENGTH:
        return value
    # Name the key only: echoing the value would put the content we are refusing into an error.
    raise JobPayloadError(f"Job payload '{key}' must be an identifier (int, UUID, bool, None or a short string)")


def enqueue(name, **payload):
    clean = {key: _identifier(key, value) for key, value in payload.items()}
    return Job.objects.create(name=name, payload=clean)


def run_pending(limit=100):
    """Run pending jobs oldest first and return how many were attempted.

    A failing job is recorded as failed (with its error) and never blocks the ones behind it. A job's
    own database writes roll back if it fails. Rows are locked with SKIP LOCKED so several workers
    can run side by side.
    """
    attempted = 0
    while attempted < limit:
        with transaction.atomic():
            job = (
                Job.objects.select_for_update(skip_locked=True)
                .filter(status=Job.PENDING)
                .order_by("id")
                .first()
            )
            if job is None:
                break
            try:
                handler = HANDLERS.get(job.name)
                if handler is None:
                    raise LookupError(f"No handler registered for job '{job.name}'")
                with transaction.atomic():
                    handler(**job.payload)
            except Exception as exc:
                # Exception messages often echo tenant content, so only the class is kept or logged.
                job.status = Job.FAILED
                job.error = type(exc).__name__
                logger.warning("Job %s (%s) failed: %s", job.pk, job.name, job.error)
            else:
                job.status = Job.DONE
            job.attempts += 1
            job.finished_at = timezone.now()
            job.save()
        attempted += 1
    return attempted
