from django.urls import path

from . import views

app_name = "wallets"

urlpatterns = [
    path("", views.wallets_home, name="wallets"),
    path("add/", views.add_wallet, name="add_wallet"),
    path("<int:pk>/update/", views.update_wallet, name="update_wallet"),
    path("<int:pk>/toggle/", views.toggle_wallet, name="toggle_wallet"),
    path("<int:pk>/delete/", views.delete_wallet, name="delete_wallet"),
]
