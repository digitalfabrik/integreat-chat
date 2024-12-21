"""
URL configuration for integreat_chat project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include

from integreat_chat.search.views import search_documents
from integreat_chat.translate.views import translate_message

urlpatterns = [
    # Support legacy URLs
    path('chatanswers/search_documents/', search_documents, name="redir_search"),
    path('chatanswers/translate_message/', translate_message, name="redir_translate"),

    path('keywords/', include('integreat_chat.keywords.urls')),
    path('chatanswers/', include('integreat_chat.chatanswers.urls')),
    path('search/', include('integreat_chat.search.urls')),
    path('translate/', include('integreat_chat.translate.urls')),
]
