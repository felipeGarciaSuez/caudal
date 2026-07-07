from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    # PWA manifest, rendered as a template so {% static %} resolves the hashed
    # icon filenames produced by WhiteNoise in prod.
    path(
        "manifest.webmanifest",
        TemplateView.as_view(
            template_name="manifest.webmanifest",
            content_type="application/manifest+json",
        ),
        name="manifest",
    ),
    # Admin path is configurable (ADMIN_URL) so prod can hide it off /admin/.
    path(settings.ADMIN_URL, admin.site.urls),
    # Branded auth (single-user). LoginView uses templates/registration/login.html.
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("import/", include("apps.imports.urls")),
    path("savings/", include("apps.savings.urls")),
    path("fijos/", include("apps.budgets.urls")),
    path("billeteras/", include("apps.wallets.urls")),
    path("categorias/", include("apps.transactions.urls")),
    path("", include("apps.dashboard.urls")),
]
