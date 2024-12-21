"""
Integreat CMS helper functions
"""
import json
from urllib.request import urlopen
from urllib.parse import quote

from django.conf import settings

def get_page(path: str) -> dict:
    """
    get page object for RAG source
    """
    region = path.split("/")[1]
    cur_language = path.split("/")[2]
    pages_url = (
        f"https://{settings.INTEGREAT_CMS_DOMAIN}/api/v3/{region}/"
        f"{cur_language}/children/?url={path}&depth=0"
    )
    encoded_url = quote(pages_url, safe=':/=?&')
    with urlopen(encoded_url) as response:
        return json.loads(response.read())[0]
