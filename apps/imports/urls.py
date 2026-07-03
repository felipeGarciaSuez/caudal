from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.import_view, name="import"),
    path("review/", views.review_view, name="review"),
    path("review/<int:tx_id>/", views.review_update, name="review_update"),
    path("review/<int:tx_id>/delete/", views.review_delete, name="review_delete"),
]
