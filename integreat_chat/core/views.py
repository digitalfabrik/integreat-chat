"""
Core application views
"""
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from integreat_chat.core.utils.health import check_health

LOGGER = logging.getLogger(__name__)


@csrf_exempt
async def health(request):
    """
    Health check endpoint.

    Validates connectivity to:
    - LLM server
    - OpenSearch (returns index counts and document statistics)

    Returns JSON with overall status:
    - "healthy": All services reachable
    - "degraded": One or more services unavailable
    """
    health_data = await check_health()
    return JsonResponse(health_data)
