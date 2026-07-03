from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.import_view, name="import"),
    path("review/", views.review_view, name="review"),
    path("review/<int:tx_id>/", views.review_update, name="review_update"),
    path("review/<int:tx_id>/delete/", views.review_delete, name="review_delete"),
    path("rules/", views.rules_home, name="rules"),
    path("rules/add/", views.add_rule, name="add_rule"),
    path("rules/<int:pk>/update/", views.update_rule, name="update_rule"),
    path("rules/<int:pk>/toggle/", views.toggle_rule, name="toggle_rule"),
    path("rules/<int:pk>/delete/", views.delete_rule, name="delete_rule"),
]
