from django.db import models


class Job(models.Model):
    """A queued background job. Global system table, deliberately outside row-level security.

    See docs/adr/0001-jobs-are-global.md. `payload` holds identifiers only and `error` holds only an
    exception class name, so the table never contains tenant content.
    """

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"

    name = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, default=PENDING, db_index=True)
    error = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
