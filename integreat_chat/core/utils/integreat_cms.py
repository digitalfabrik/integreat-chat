"""
Integreat CMS helper functions
"""
from urllib.parse import quote

import requests
from django.conf import settings

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
    region = path.split("/")[1]
    cur_language = path.split("/")[2]
    headers = {"X-Integreat-Development": "true"}
    pages_url = (
        f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{region}/"
        f"{cur_language}/children/?url={path}&depth=0"
    )
    encoded_url = quote(pages_url, safe=':/=?&')
    return requests.get(encoded_url, timeout=15, headers=headers).json()[0]

def get_pages(region_slug: str, language_slug: str) -> list[dict]:
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