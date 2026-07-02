from django.urls import path

from . import views

app_name = "budgets"

urlpatterns = [
    path("", views.fixed_home, name="fixed"),
    path("add/", views.add_recurring, name="add_recurring"),
    path("<int:pk>/update/", views.update_recurring, name="update_recurring"),
    path("<int:pk>/toggle/", views.toggle_recurring, name="toggle_recurring"),
    path("<int:pk>/delete/", views.delete_recurring, name="delete_recurring"),
]
