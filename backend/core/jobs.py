"""Postgres-backed job queue (D10): no broker. Tests call run_pending() in-process."""

from django.db import transaction
from django.utils import timezone

from .models import Job

HANDLERS = {}


def register(name):
    def decorator(func):
        HANDLERS[name] = func
        return func

    return decorator


def enqueue(name, **payload):
    return Job.objects.create(name=name, payload=payload)


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
                job.status = Job.FAILED
                job.error = f"{type(exc).__name__}: {exc}"
            else:
                job.status = Job.DONE
            job.attempts += 1
            job.finished_at = timezone.now()
            job.save()
        attempted += 1
    return attempted
