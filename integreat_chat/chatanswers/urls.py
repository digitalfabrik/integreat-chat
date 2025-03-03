from django.urls import path
from . import views

urlpatterns = [
    path("extract_answer/", views.chat, name="extract_answer"),
    path("chat/", views.chat, name="chat"),
]
