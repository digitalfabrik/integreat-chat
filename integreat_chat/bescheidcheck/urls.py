from django.urls import path

from . import views

urlpatterns = [
    path("", views.ui, name="bescheidcheck_ui"),
    path("analyze/", views.analyze, name="bescheidcheck_analyze"),
    path(
        "analyze/<str:language>/",
        views.analyze,
        name="bescheidcheck_analyze_language",
    ),
    path(
        "generate_question/",
        views.generate_question,
        name="bescheidcheck_generate_question",
    ),
    path(
        "generate_question/<str:language>/",
        views.generate_question,
        name="bescheidcheck_generate_question_language",
    ),
]
