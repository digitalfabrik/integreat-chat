"""
Index pages for region & language
"""

from django.core.management.base import BaseCommand, CommandError

from ...tasks import update_index

class Command(BaseCommand):
    """
    Index pages for region & language
    """
    help = "Index pages for region & language"

    def add_arguments(self, parser):
        parser.add_argument("region", type=str)
        parser.add_argument("language", type=str)
        parser.add_argument(
            "--full",
            action="store_true",
            help="Re-create full index",
        )

    def handle(self, *args, **options):
        if "region" not in options or "language" not in options:
            raise CommandError('missing region or language argument')
        region_slug = options["region"]
        language_slug = options["language"]
        update_index.apply_async([region_slug, language_slug, not options["full"]])
        self.stdout.write(self.style.SUCCESS(  # pylint: disable=no-member
            f"Queued indexing pages for region {region_slug} and language {language_slug}"
        ))
