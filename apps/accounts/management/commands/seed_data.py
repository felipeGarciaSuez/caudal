"""Seed real wallets and base categories for a user (idempotent).

Usage:
    uv run python manage.py seed_data            # uses first superuser
    uv run python manage.py seed_data --user me  # by username
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.imports.models import CategoryRule
from apps.savings.models import Asset
from apps.transactions.models import Category
from apps.wallets.models import Wallet

User = get_user_model()

WALLETS = [
    ("ICBC", Wallet.Kind.BANK),
    ("Galicia", Wallet.Kind.BANK),
    ("Mercado Pago", Wallet.Kind.WALLET),
    ("Ualá", Wallet.Kind.WALLET),
    ("Personal Pay", Wallet.Kind.WALLET),
    ("Efectivo", Wallet.Kind.CASH),
    ("ICBC Visa", Wallet.Kind.CREDIT_CARD),
    ("ICBC Master", Wallet.Kind.CREDIT_CARD),
    ("Galicia Visa", Wallet.Kind.CREDIT_CARD),
]

# (name, kind, icon) — icon is a Lucide icon name (see apps/dashboard/templatetags/icons.py).
# Broad buckets on purpose: a specific bill (Flow, TGI, Expensas, Gym) is NOT a
# category, it's the *description* of a fixed expense the user loads under one of
# these. The monthly checklist labels each row by that description, so keeping
# categories general avoids a taxonomy cluttered with one-off line items.
# This is only a starting point: every category is editable/removable from the app.
CATEGORIES = [
    # Fijos: obligaciones recurrentes (alquiler, servicios, suscripciones...).
    ("Vivienda", Category.Kind.FIXED, "home"),
    ("Servicios", Category.Kind.FIXED, "lightbulb"),
    ("Suscripciones", Category.Kind.FIXED, "tv"),
    ("Salud", Category.Kind.FIXED, "heart-pulse"),
    ("Impuestos", Category.Kind.FIXED, "receipt"),
    # Variables: gasto necesario pero que cambia mes a mes.
    ("Supermercado", Category.Kind.VARIABLE, "shopping-cart"),
    ("Nafta", Category.Kind.VARIABLE, "fuel"),
    ("Farmacia", Category.Kind.VARIABLE, "pill"),
    ("Ropa", Category.Kind.VARIABLE, "shirt"),
    ("Hogar", Category.Kind.VARIABLE, "sofa"),
    ("Ocio", Category.Kind.VARIABLE, "tv"),
    # Hormiga: los chicos y frecuentes, el foco de la app.
    ("Delivery", Category.Kind.ANT, "bike"),
    ("Kiosco", Category.Kind.ANT, "cookie"),
    ("Café", Category.Kind.ANT, "coffee"),
    ("Transporte/Uber", Category.Kind.ANT, "car"),
    ("Apps", Category.Kind.ANT, "layout-grid"),
    ("Compras chicas", Category.Kind.ANT, "shopping-bag"),
]

# keyword -> category name. Keywords match (case-insensitive) inside the description.
RULES = [
    ("RAPPI", "Delivery"),
    ("PEDIDOSYA", "Delivery"),
    ("PEDIDOS YA", "Delivery"),
    ("MCDONALD", "Delivery"),
    ("YPF", "Nafta"),
    ("SHELL", "Nafta"),
    ("AXION", "Nafta"),
    ("PUMA", "Nafta"),
    ("NETFLIX", "Suscripciones"),
    ("SPOTIFY", "Suscripciones"),
    ("DISNEY", "Suscripciones"),
    ("HBO", "Suscripciones"),
    ("YOUTUBE", "Suscripciones"),
    ("UBER", "Transporte/Uber"),
    ("CABIFY", "Transporte/Uber"),
    ("DIDI", "Transporte/Uber"),
    ("SUBE", "Transporte/Uber"),
    ("CARREFOUR", "Supermercado"),
    ("COTO", "Supermercado"),
    ("DIA ", "Supermercado"),
    ("JUMBO", "Supermercado"),
    ("VEA", "Supermercado"),
    ("SUPERMERCADO", "Supermercado"),
    ("FARMACIA", "Farmacia"),
    ("FARMACITY", "Farmacia"),
    ("KIOSCO", "Kiosco"),
    ("CAFE", "Café"),
    ("COFFEE", "Café"),
    ("BRULEE", "Café"),
    ("STARBUCKS", "Café"),
    # Servicios / suscripciones que aparecen en banco y tarjeta ICBC
    ("PRIMEVIDEO", "Suscripciones"),
    ("PRIME VIDEO", "Suscripciones"),
    ("ANTHROPIC", "Suscripciones"),
    ("GOOGLE", "Suscripciones"),
    ("APPLE", "Suscripciones"),
    ("SPLICE", "Suscripciones"),
    ("SOUNDCLOUD", "Suscripciones"),
    ("SUNO", "Suscripciones"),
    ("SUPERCELL", "Apps"),
    ("INSTANT GAMING", "Apps"),
    # Compras / ocio / servicios
    ("MERCADOLIBRE", "Compras chicas"),
    ("NATURA", "Ropa"),
    ("CROSSCLOTHING", "Ropa"),
    ("SHOWCASE", "Ocio"),
    ("CINE", "Ocio"),
    ("PASAJES", "Transporte/Uber"),
    ("AGUAS ASSA", "Servicios"),
    ("PAGO ROSARIO", "Impuestos"),
]


# Savings assets. These are global (not per-user). Start with the two the owner
# actually uses: dólar billete and dólar cripto (USDT). Crypto/stocks: add later.
# (symbol, name, kind)
ASSETS = [
    ("USD", "Dólar billete", Asset.Kind.FIAT_CASH),
    ("USDT", "Dólar cripto (USDT)", Asset.Kind.STABLECOIN),
]

# NOTE: no fixed expenses (RecurringExpense) are seeded on purpose. A fresh user
# gets categories/wallets/rules and loads their own fijos so the amounts and the
# checklist reflect their real life from day one, not placeholder numbers.


class Command(BaseCommand):
    help = "Crea wallets, categorías y reglas base (idempotente). No carga fijos."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="username; por defecto, el primer superuser")

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("user"))

        wallets_created = 0
        for name, kind in WALLETS:
            _, created = Wallet.objects.get_or_create(
                owner=user, name=name, defaults={"kind": kind}
            )
            wallets_created += int(created)

        categories_created = 0
        categories = {}
        for name, kind, icon in CATEGORIES:
            cat, created = Category.objects.get_or_create(
                owner=user, name=name, defaults={"kind": kind, "icon": icon}
            )
            # Keep the icon in sync (e.g. migrating older emoji icons to Lucide names).
            if not created and cat.icon != icon:
                cat.icon = icon
                cat.save(update_fields=["icon"])
            categories[name] = cat
            categories_created += int(created)

        rules_created = 0
        for priority, (keyword, cat_name) in enumerate(RULES, start=1):
            category = categories.get(cat_name)
            if category is None:
                continue
            _, created = CategoryRule.objects.get_or_create(
                owner=user,
                keyword=keyword,
                category=category,
                defaults={"priority": priority},
            )
            rules_created += int(created)

        assets_created = 0
        for symbol, name, kind in ASSETS:
            _, created = Asset.objects.get_or_create(
                symbol=symbol, defaults={"name": name, "kind": kind}
            )
            assets_created += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed para '{user}': {wallets_created} wallets, "
                f"{categories_created} categorías, {rules_created} reglas "
                f"y {assets_created} activos nuevos."
            )
        )

    def _resolve_user(self, username):
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(f"No existe el usuario '{username}'.") from exc
        user = User.objects.filter(is_superuser=True).order_by("id").first()
        if not user:
            raise CommandError("No hay superuser. Creá uno con 'createsuperuser' o pasá --user.")
        return user
