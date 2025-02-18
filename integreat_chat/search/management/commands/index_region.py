"""
Index pages for region & language
"""

from django.core.management.base import BaseCommand, CommandError
from integreat_chat.core.utils.integreat_cms import get_region_languages

from ...tasks import update_index


class Command(BaseCommand):
    """
    Index pages for region & language
    """
    help = "Index pages for region & language"

    def add_arguments(self, parser):
        parser.add_argument("region", type=str)

    def handle(self, *args, **options):
        if "region" not in options:
            raise CommandError('missing region argument')
        region_slug = options["region"]
        for language_slug in get_region_languages(region_slug):
            update_index.apply_async([region_slug, language_slug])
            self.stdout.write(self.style.SUCCESS(  # pylint: disable=no-member
                f"Queued indexing pages for region {region_slug} and language {language_slug}"
            ))
