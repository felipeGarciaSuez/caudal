from django.urls import path

from . import views

app_name = "savings"

urlpatterns = [
    path("", views.savings_home, name="home"),
    path("add/", views.add_movement, name="add_movement"),
    path("price/", views.set_price, name="set_price"),
    path("m/<int:mv_id>/delete/", views.delete_movement, name="delete_movement"),
]
