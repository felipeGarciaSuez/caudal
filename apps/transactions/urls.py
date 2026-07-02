from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    path("", views.categories_home, name="categories"),
    path("add/", views.add_category, name="add_category"),
    path("<int:pk>/update/", views.update_category, name="update_category"),
    path("<int:pk>/delete/", views.delete_category, name="delete_category"),
]
