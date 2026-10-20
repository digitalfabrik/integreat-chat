"""
Explanation pages for the bescheidcheck app.

Every supported Bescheid type has an editorial page in the Integreat CMS
region ``bescheid-check`` whose slug equals the classified type (e.g.
``ablehnung-unzulässig``). After classification the matching page is
fetched and shown above the translation.

Classification runs on the German document, so the slug is always
German. The German page is fetched first; its ``available_languages``
then tells us whether an editorial translation into the user's target
language exists, in which case that one is shown instead.
"""

import logging
from urllib.parse import quote

import aiohttp
from django.conf import settings

from .sanitizer import sanitize_html

LOGGER = logging.getLogger(__name__)

LANGUAGE = "de"
REGION = "bescheid-check"

# ``unsupported`` is the pipeline's internal sentinel for "could not be
# typed"; the CMS names that page after what the user sees instead.
SLUG_BY_TYPE = {"unsupported": "bescheid-nicht-erkannt"}


async def _fetch_page(
    session: aiohttp.ClientSession, language: str, path: str
) -> dict | None:
    """
    Fetch one explanation page from the CMS, or None if it does not exist.

    param language: CMS language slug the page is requested in
    param path: CMS page path, e.g. ``/bescheid-check/de/ladung-anhörung``
    """
    url = quote(
        f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{REGION}/{language}"
        f"/children/?depth=2&url={path}",
        safe=":/=?&",
    )
    async with session.get(
        url,
        headers={"X-Integreat-Development": "true"},
        timeout=aiohttp.ClientTimeout(total=15),
    ) as response:
        if response.status != 200:
            LOGGER.info("explanation: CMS returned %s for %s", response.status, path)
            return None
        pages = await response.json()
    if not isinstance(pages, list) or not pages:
        return None
    return pages[0]


async def _translated_page(
    session: aiohttp.ClientSession,
    german_page: dict,
    target_language: str | None,
) -> dict | None:
    """
    Fetch the editorial translation of ``german_page`` into
    ``target_language``, or None when there is none to use.
    """
    if not target_language or target_language == LANGUAGE:
        return None
    translations = german_page.get("available_languages") or {}
    path = (translations.get(target_language) or {}).get("path")
    if not path:
        LOGGER.info(
            "explanation: no %s translation for %s, keeping German",
            target_language,
            german_page.get("path"),
        )
        return None
    return await _fetch_page(session, target_language, path)


async def get_explanation(
    bescheid_type: str,
    target_language: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> dict | None:
    """
    Look up the explanation page for a classified Bescheid type.

    param bescheid_type: the classified type, used as the CMS page slug
    param target_language: the user's language; when the German page has
        an editorial translation into it, that translation is returned
    return: dict with ``title``, ``content`` (sanitized HTML) and
        ``url``, or None when no page exists or the CMS is unreachable
    """
    if bescheid_type not in settings.BESCHEID_SUPPORTED_TYPES:
        return None
    slug = SLUG_BY_TYPE.get(bescheid_type, bescheid_type)

    if session is None:
        async with aiohttp.ClientSession() as own_session:
            return await get_explanation(
                bescheid_type, target_language, session=own_session
            )

    try:
        page = await _fetch_page(session, LANGUAGE, f"/{REGION}/{LANGUAGE}/{slug}")
        if page is not None:
            page = await _translated_page(session, page, target_language) or page
    except (aiohttp.ClientError, ValueError) as exc:
        LOGGER.warning("explanation: could not fetch %s: %s", slug, exc)
        return None
    if page is None:
        return None

    content = sanitize_html(page.get("content") or "")
    if not content:
        return None
    return {
        "title": page.get("title") or "",
        "content": content,
        "url": page.get("url") or "",
    }
