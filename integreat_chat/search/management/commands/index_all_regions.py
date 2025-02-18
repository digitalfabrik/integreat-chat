"""
Index pages for all configured regions
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from integreat_chat.core.utils.integreat_cms import get_region_languages

from ...tasks import update_index

class Command(BaseCommand):
    """
    Index pages for all configured regions
    """
    help = "Index pages for all configured regions"

    def handle(self, *args, **options):
        for region_slug in settings.INTEGREAT_REGIONS:
            for language_slug in get_region_languages(region_slug):
                update_index.apply_async([region_slug, language_slug])
                self.stdout.write(self.style.SUCCESS(  # pylint: disable=no-member
                    f"Queued indexing pages for region {region_slug} and language {language_slug}"
                ))
