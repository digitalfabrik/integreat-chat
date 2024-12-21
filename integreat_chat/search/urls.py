from django.urls import path
from . import views

urlpatterns = [
    path("documents/", views.search_documents, name="search_documents"),
    path("update_vdb/", views.update_vdb, name="update_vdb")
]
