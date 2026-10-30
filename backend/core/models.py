from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("An email address is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """The sign-in identity: an email address and a password (D40 (5)).

    Which companies a user may act in, and as what, lives in `CompanyAccess`, not here.
    """

    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    # Marks a firm accountant for good, so one created before any company still gets access to later ones.
    # Set only by the operator command; the database default lets the SQL functions create users without it.
    is_accountant = models.BooleanField(default=False, db_default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = "email"

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_unique_ignoring_case")]

    def __str__(self):
        return self.email


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
    ROLES = [(OWNER, _("Client owner")), (STAFF, _("Client staff")), (ACCOUNTANT, _("Firm accountant"))]

    user = models.ForeignKey("core.User", on_delete=models.CASCADE, related_name="company_access")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="access")
    role = models.CharField(max_length=20, choices=ROLES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "company"], name="one_access_row_per_user_company"),
            models.UniqueConstraint(
                fields=["company"], condition=models.Q(role="owner"), name="one_owner_per_company"
            ),
            models.CheckConstraint(condition=models.Q(role__in=["owner", "staff", "accountant"]), name="known_role"),
        ]


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


class LoginFailure(models.Model):
    """One failed sign-in attempt, for throttling. Only the hash of the email address is kept.

    The web role has no direct access to this table; it goes through the functions in migration 0007.
    """

    email_hash = models.CharField(max_length=64, db_index=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)


class AuthToken(models.Model):
    """A single-use, expiring link: a password reset or an invitation (D40 (5)).

    Only the SHA-256 hash of the token is stored, so a database reader cannot use a link. The web role has
    no direct access to this table; it goes through the functions in migrations 0009 and 0010.
    """

    RESET = "reset"
    INVITE = "invite"

    PURPOSES = [(RESET, "Password reset"), (INVITE, "Invitation")]

    purpose = models.CharField(max_length=10, choices=PURPOSES)
    token_hash = models.CharField(max_length=64, unique=True)
    email = models.EmailField()
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, blank=True)
    user = models.ForeignKey("core.User", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
