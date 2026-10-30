from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core import services, tokens


class Command(BaseCommand):
    help = (
        "Create a firm accountant with access to every pilot company and email them a link to choose a password. "
        "Accountants are created only here, never by a client (D48)."
    )

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        try:
            accountant = services.create_accountant(email)
        except services.EmailInUse as error:
            raise CommandError("That address already has an account.") from error
        base = settings.BASE_URL.rstrip("/")
        tokens.request_password_reset(accountant.email, lambda raw: f"{base}/reset/{raw}/")
        self.stdout.write(f"Created accountant {accountant.email} and emailed a password link.")
