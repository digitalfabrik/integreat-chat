"""
Integreat CMS helper functions
"""
import asyncio
import logging
from urllib.parse import quote

import aiohttp
import requests
from django.conf import settings

LOGGER = logging.getLogger("django")

def get_region_languages(region: str) -> list[str]:
    """
    get all language slugs of a given region
    """
    url = f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{region}/languages/"
    headers = {"X-Integreat-Development": "true"}
    languages = requests.get(url, timeout=15, headers=headers).json()
    return [language["code"] for language in languages]

def get_page(path: str) -> dict:
    """
    get page object for RAG source
    """
    path = (
        path
        .replace(f"https://{settings.INTEGREAT_APP_DOMAIN}", "")
        .replace(f"https://{settings.INTEGREAT_CMS_DOMAIN}", "")
    )
    LOGGER.debug("APP Domain: %s", settings.INTEGREAT_APP_DOMAIN)
    LOGGER.debug("CMS Domain: %s", settings.INTEGREAT_CMS_DOMAIN)
    LOGGER.debug("Path: %s", path)
    region = path.split("/")[1]
    cur_language = path.split("/")[2]
    headers = {"X-Integreat-Development": "true"}
    pages_url = (
        f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{region}/"
        f"{cur_language}/children/?url={path}&depth=0"
    )
    encoded_url = quote(pages_url, safe=':/=?&')
    LOGGER.debug("Pages url-%s", pages_url)
    LOGGER.debug("Encoded url-%s", encoded_url)
    return requests.get(encoded_url, timeout=15, headers=headers).json()[0]

async def async_get_page(session: aiohttp.ClientSession, path: str, retry: int = 0) -> dict:
    """
    Fetch a single page object asynchronously.

    :param session: aiohttp session used for the Integreat CMS request
    :param path: path of the page to be requested
    :param retry: retry count to break recursion on failed requests
    :return: Integreat CMS page data
    """
    path = (
        path
        .replace(f"https://{settings.INTEGREAT_APP_DOMAIN}", "")
        .replace(f"https://{settings.INTEGREAT_CMS_DOMAIN}", "")
    )
    region = path.split("/")[1]
    cur_language = path.split("/")[2]
    headers = {"X-Integreat-Development": "true"}
    pages_url = (
        f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{region}/"
        f"{cur_language}/children/?url={path}&depth=0"
    )
    encoded_url = quote(pages_url, safe=':/=?&')

    async with session.get(
        encoded_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
    ) as response:
        try:
            return (await response.json())[0]
        except KeyError as exc:
            if retry < 3:
                return async_get_page(session, path, retry=retry+1)
            raise ValueError(f"Could not fetch data for {path}") from exc

async def cms_requests_session_wrapper(paths: list[str]) -> list[dict]:
    """
    Create an aiohttp session, send requests and gather responses
    """
    async with aiohttp.ClientSession() as session:
        tasks = [async_get_page(session, path) for path in paths]
        return await asyncio.gather(*tasks)

def get_pages(paths: list[str]) -> list[dict]:
    """
    Get content for multiple pages
    """
    return asyncio.run(cms_requests_session_wrapper(paths))

def get_all_pages(region_slug: str, language_slug: str) -> list[dict]:
    """
    get data from Integreat cms
    """
    headers = {"X-Integreat-Development": "true"}
    pages_url = (
        f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{region_slug}/{language_slug}/pages"
    )
    return requests.get(pages_url, timeout=30, headers=headers).json()

def get_parent_page_titles(region_slug: str, language_slug: str, path: str):
    """
    get parent page titles for a given path
    """
    headers = {"X-Integreat-Development": "true"}
    parents_url = (
        f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{region_slug}/{language_slug}/parents/?url={path}"
    )
    return requests.get(parents_url, timeout=30, headers=headers).json()