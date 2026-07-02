from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("m/<str:period>/", views.month_view, name="month"),
    path("add/", views.add_transaction, name="add_transaction"),
    path("m/<str:period>/income/", views.set_income, name="set_income"),
    path(
        "m/<str:period>/c/<int:category_id>/",
        views.category_detail,
        name="category_detail",
    ),
    path("tx/<int:tx_id>/toggle-paid/", views.toggle_paid, name="toggle_paid"),
    path("tx/<int:tx_id>/amount/", views.update_amount, name="update_amount"),
    path("tx/<int:tx_id>/edit/", views.edit_transaction, name="edit_transaction"),
    path("tx/<int:tx_id>/delete/", views.delete_transaction, name="delete_transaction"),
]
