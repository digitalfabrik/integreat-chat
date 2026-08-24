from django.urls import path

from . import views

urlpatterns = [
    path("", views.ui, name="bescheidcheck_ui"),
    path("analyze/", views.analyze, name="bescheidcheck_analyze"),
]
