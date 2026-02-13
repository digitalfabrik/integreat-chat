from django.urls import path
from . import views

urlpatterns = [
    path("message/", views.translate_message, name="translate_message"),
    path("message_to_region_languages/", views.message_to_region_languages, name="message_to_region_languages"),
    path("detect/", views.detect_language, name="detect_language"),
]
