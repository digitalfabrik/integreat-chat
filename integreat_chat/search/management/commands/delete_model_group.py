"""
Index pages for region & language
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from integreat_chat.search.services.opensearch import OpenSearchSetup


class Command(BaseCommand):
    """
    Index pages for region & language
    """
    help = "Index pages for region & language"

    def handle(self, *args, **options):
        oss = OpenSearchSetup(password=settings.OPENSEARCH_PASSWORD)
        oss.delete_model_group()
