from django.urls import path
from . import views

urlpatterns = [
    path("translate_message/", views.translate_message, name="translate_message"),
]
