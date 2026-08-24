from django.http import JsonResponse


def page_keywords(request, page_path):
    """
    Extract keywords for page with give path
    """
    # keyword extraction code goes here
    return JsonResponse({"keywords":[]})
