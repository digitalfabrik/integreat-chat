from django.urls import path
from . import views

urlpatterns = [
    path("extract_answer/", views.extract_answer, name="extract_answer"),

    # Support legacy URLs
    path("/chatanswers/search_documents/", views.redirect_search, name="redir_search"),
    path("/chatanswers/translate_message/", views.redirect_translate, name="redir_translate"),
]
