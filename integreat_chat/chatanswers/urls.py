from django.urls import path
from . import views

urlpatterns = [
    path("extract_answer/", views.extract_answer, name="extract_answer"),
]
