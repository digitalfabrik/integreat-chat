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
        group_id, model_id, model_id_ce = oss.setup()
        self.stdout.write(
            self.style.SUCCESS(  # pylint: disable=no-member
                f'Successfully set up OpenSearch. Change the following settings '
                f'in the OPENSEARCH section of your config:\n'
                f'MODEL_GROUP_ID = {group_id}\n'
                f'MODEL_ID_EMBEDDING_MODEL = {model_id}\n'
                f'MODEL_ID_CROSSENCODER_MODEL = {model_id_ce}\n'
            )
        )
