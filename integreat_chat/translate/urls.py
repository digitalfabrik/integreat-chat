from django.urls import path
from . import views

urlpatterns = [
    path("message/", views.translate_message, name="translate_message"),
]
