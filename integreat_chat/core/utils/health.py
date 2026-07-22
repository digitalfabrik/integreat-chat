"""
Health check utilities for Integreat Chat
"""
import logging
from datetime import datetime, timezone

import aiohttp
from django.conf import settings
from integreat_chat.search.services.opensearch import OpenSearch

LOGGER = logging.getLogger(__name__)


async def check_llm_health() -> dict:
    """
    Check if LLM server is reachable.

    Returns:
        dict with 'status' (healthy/unavailable) and 'server' URL
    """
    result = {
        "status": "unavailable",
        "server": settings.LLM_SERVER,
    }

    try:
        url = f"{settings.LLM_SERVER}/chat/completions"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={
                    "model": settings.RAG_MODEL,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status < 500:
                    result["status"] = "healthy"
                else:
                    LOGGER.warning("LLM server returned HTTP %s", response.status)
    except Exception as e:
        LOGGER.warning("LLM health check failed: %s", e)

    return result


def check_opensearch_health() -> dict:
    """
    Check OpenSearch connectivity and gather index statistics.

    Returns:
        dict with 'status' (healthy/unavailable), 'indexes' list,
        'total_indexes' count, and 'total_documents' count
    """
    result = {
        "status": "unavailable",
        "total_indexes": 0,
        "total_documents": 0,
    }

    try:
        opensearch = OpenSearch(password=settings.OPENSEARCH_PASSWORD)
        indexes = opensearch.get_all_indexes()
        
        if not indexes:
            return result

        result["total_indexes"] = len(indexes)
        result["total_documents"] = sum(idx["document_count"] for idx in indexes)
        result["status"] = "healthy"

    except Exception as e:
        LOGGER.warning("OpenSearch health check failed: %s", e)

    return result


async def check_health() -> dict:
    """
    Perform comprehensive health check.

    Returns:
        dict with overall status, timestamp, and detailed check results
    """
    llm_check = await check_llm_health()
    opensearch_check = check_opensearch_health()

    # Determine overall status
    if llm_check["status"] == "healthy" and opensearch_check["status"] == "healthy":
        overall_status = "healthy"
    else:
        overall_status = "degraded"

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_indexes": opensearch_check["total_indexes"],
        "total_documents": opensearch_check["total_documents"],
        "llm": llm_check,
        "opensearch": opensearch_check,
    }
