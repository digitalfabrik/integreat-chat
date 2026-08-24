from django.urls import path

from . import views

urlpatterns = [
    path("page/<str:page_path>", views.page_keywords, name="page_keywords"),
]
