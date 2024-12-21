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

from integreat_chat.chatanswers.views import redirect_search, redirect_translate

urlpatterns = [
    # Support legacy URLs
    path("/chatanswers/search_documents/", redirect_search, name="redir_search"),
    path("/chatanswers/translate_message/", redirect_translate, name="redir_translate"),

    path('keywords/', include('integreat_chat.keywords.urls')),
    path('chatanswers/', include('integreat_chat.chatanswers.urls')),
    path('search/', include('integreat_chat.search.urls')),
    path('translate/', include('integreat_chat.translate.urls')),
]
