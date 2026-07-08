from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.import_view, name="import"),
    path("<int:batch_id>/delete/", views.import_delete, name="import_delete"),
    path("rules/", views.rules_home, name="rules"),
    path("rules/add/", views.add_rule, name="add_rule"),
    path("rules/<int:pk>/update/", views.update_rule, name="update_rule"),
    path("rules/<int:pk>/toggle/", views.toggle_rule, name="toggle_rule"),
    path("rules/<int:pk>/delete/", views.delete_rule, name="delete_rule"),
]
