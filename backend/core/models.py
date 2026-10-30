from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """The sign-in identity. Deliberately empty for now: ticket 02b adds email login and the rest.

    It exists so `CompanyAccess` can point at it from the first migration; swapping the user model
    after tables reference it is painful in Django.
    """


class Company(models.Model):
    """A tenant: one business whose data is isolated from every other company (D11)."""

    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class CompanyAccess(models.Model):
    """Which users may act in which company, and in what role (D40).

    This table is what row-level security reads: a row of a tenant table is visible only when its
    company id is among the signed-in user's rows here. There is no bypass role.
    """

    OWNER = "owner"
    STAFF = "staff"
    ACCOUNTANT = "accountant"
    ROLES = [(OWNER, "Client owner"), (STAFF, "Client staff"), (ACCOUNTANT, "Firm accountant")]

    user = models.ForeignKey("core.User", on_delete=models.CASCADE, related_name="company_access")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="access")
    role = models.CharField(max_length=20, choices=ROLES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "company"], name="one_access_row_per_user_company")]


class TenantModel(models.Model):
    """Base for every business table. Pair it with `core.rls.enable_tenant_rls` in the migration."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, db_index=True)

    class Meta:
        abstract = True


class Job(models.Model):
    """A queued background job.

    Interim: no company id and no row-level security yet; ticket 02 adds both (see
    docs/adr/0001-job-queue-and-tenancy.md). `payload` holds identifiers only and `error` holds only an
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
