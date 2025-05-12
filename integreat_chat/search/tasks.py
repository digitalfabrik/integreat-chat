from celery import shared_task
from django.conf import settings

from integreat_chat.search.services.opensearch import OpenSearchSetup
from integreat_chat.core.utils.integreat_cms import get_region_languages



@shared_task
def update_index(region_slug: str, language_slug: str, differential: bool = True) -> None:
    """
    param region_slug: slug of the region which should be updated
    param language_slug: slug of the language (BCP47 tag) that should be updated
    """
    oss = OpenSearchSetup(password=settings.OPENSEARCH_PASSWORD)
    print(f"Indexing pages for region {region_slug} and language {language_slug}. Differential {differential}.")
    if not differential:
        print(oss.delete_index(f"{region_slug}_{language_slug}"))
        print(oss.create_index(f"{region_slug}_{language_slug}"))
    oss.index_pages(region_slug, language_slug, differential)


@shared_task
def update_search_indexes() -> None:
    """
    Update all search indexes
    """
    for region_slug in settings.INTEGREAT_REGIONS:
        for language_slug in get_region_languages(region_slug):
            update_index.apply_async([region_slug, language_slug])
