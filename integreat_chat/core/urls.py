"""
URL configuration for integreat_chat project.
"""
from django.urls import path, include

from integreat_chat.search.views import search_documents
from integreat_chat.translate.views import translate_message
from integreat_chat.core.views import health

urlpatterns = [
    # Support legacy URLs
    path('chatanswers/search_documents/', search_documents, name="redir_search"),
    path('chatanswers/translate_message/', translate_message, name="redir_translate"),

    path('health/', health, name="health"),
    path('keywords/', include('integreat_chat.keywords.urls')),
    path('chatanswers/', include('integreat_chat.chatanswers.urls')),
    path('search/', include('integreat_chat.search.urls')),
    path('translate/', include('integreat_chat.translate.urls')),
]
