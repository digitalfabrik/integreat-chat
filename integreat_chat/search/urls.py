from django.urls import path
from . import views

urlpatterns = [
    path("", views.search, name="search"),
    path("documents/", views.search_documents, name="search_documents"),
    path(
        "opensearch/<slug:region>/<slug:language>/",
        views.search_opensearch,
        name="search_opensearh"
    )
]
