"""
DEVELOPMENT ONLY: removes all verification logs from the demo database.

Normal code can not delete logs (that protects the audit trail). This command
uses a direct SQL statement and refuses to run when DEBUG is False.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from verification.models import VerificationLog


class Command(BaseCommand):
    help = "DEVELOPMENT ONLY: delete all demo verification logs."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Skip the confirmation question.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refused: this command only works when DEBUG=True.")

        if not options["yes"]:
            answer = input("This permanently removes ALL verification logs. Type YES: ")
            if answer.strip() != "YES":
                raise CommandError("Cancelled. Nothing was deleted.")

        table = VerificationLog._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table}")

        self.stdout.write(self.style.SUCCESS("All demo verification logs were removed."))