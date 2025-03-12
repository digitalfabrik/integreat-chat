"""
Index pages for region & language
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from integreat_chat.search.services.opensearch import OpenSearch

class Command(BaseCommand):
    """
    Index pages for region & language
    """
    help = "Index pages for region & language"

    def add_arguments(self, parser):
        parser.add_argument("region", type=str)
        parser.add_argument("language", type=str)
        parser.add_argument("message", type=str)

    def handle(self, *args, **options):
        if "region" not in options or "language" not in options or "message" not in options:
            raise CommandError('missing region, language, or message argument')
        oss = OpenSearch(password=settings.OPENSEARCH_PASSWORD)
        documents = oss.reduce_search_result(
            oss.search(options["region"], options["language"], options["message"]),
            deduplicate=True
        )
        for document in documents:
            print(f"* {document['score']:.2f} [{document['title']}] ({document['url']})")
