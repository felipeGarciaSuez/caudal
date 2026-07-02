"""Seed real wallets and base categories for a user (idempotent).

Usage:
    uv run python manage.py seed_data            # uses first superuser
    uv run python manage.py seed_data --user me  # by username
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.budgets.models import RecurringExpense
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
CATEGORIES = [
    # Fijos — "Gastos Vivienda" agrupa (parent) los del depa; ver VIVIENDA_CHILDREN.
    ("Gastos Vivienda", Category.Kind.FIXED, "home"),
    ("Alquiler", Category.Kind.FIXED, "home"),
    ("Expensas", Category.Kind.FIXED, "building-2"),
    ("Agua", Category.Kind.FIXED, "droplet"),
    ("Luz", Category.Kind.FIXED, "lightbulb"),
    ("Gas", Category.Kind.FIXED, "flame"),
    ("TGI", Category.Kind.FIXED, "flame"),
    ("Flow", Category.Kind.FIXED, "wifi"),
    ("Teléfono", Category.Kind.FIXED, "smartphone"),
    ("Gym", Category.Kind.FIXED, "dumbbell"),
    ("Obra Social", Category.Kind.FIXED, "heart-pulse"),
    ("Suscripciones", Category.Kind.FIXED, "tv"),
    ("Impuestos", Category.Kind.FIXED, "receipt"),
    # Variables
    ("Super", Category.Kind.VARIABLE, "shopping-cart"),
    ("Nafta", Category.Kind.VARIABLE, "fuel"),
    ("Salud", Category.Kind.VARIABLE, "pill"),
    ("Ropa", Category.Kind.VARIABLE, "shirt"),
    ("Hogar", Category.Kind.VARIABLE, "sofa"),
    ("Ocio", Category.Kind.VARIABLE, "tv"),
    ("Ahorro", Category.Kind.VARIABLE, "piggy-bank"),
    # Hormiga
    ("Delivery", Category.Kind.ANT, "bike"),
    ("Kiosco", Category.Kind.ANT, "cookie"),
    ("Café", Category.Kind.ANT, "coffee"),
    ("Transporte/Uber", Category.Kind.ANT, "car"),
    ("Apps", Category.Kind.ANT, "layout-grid"),
    ("Compras chicas", Category.Kind.ANT, "shopping-bag"),
]

# Categories grouped under the "Gastos Vivienda" parent (housing costs, often
# shared with roommates) so the checklist can cluster them visually, separate
# from personal fijos (Teléfono, Gym, Obra Social, ...).
VIVIENDA_PARENT = "Gastos Vivienda"
VIVIENDA_CHILDREN = ["Alquiler", "Expensas", "Agua", "Luz", "Gas", "TGI", "Flow"]

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
    ("CARREFOUR", "Super"),
    ("COTO", "Super"),
    ("DIA ", "Super"),
    ("JUMBO", "Super"),
    ("VEA", "Super"),
    ("SUPERMERCADO", "Super"),
    ("FARMACIA", "Salud"),
    ("FARMACITY", "Salud"),
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
    ("AGUAS ASSA", "Agua"),
    ("PAGO ROSARIO", "Impuestos"),
]


# Savings assets. These are global (not per-user). Start with the two the owner
# actually uses: dólar billete and dólar cripto (USDT). Crypto/stocks: add later.
# (symbol, name, kind)
ASSETS = [
    ("USD", "Dólar billete", Asset.Kind.FIAT_CASH),
    ("USDT", "Dólar cripto (USDT)", Asset.Kind.STABLECOIN),
]


# (name, default_amount, category_name, wallet_name, day_of_month)
# Placeholder amounts — todo editable desde la app. Son los fijos "grandes" del mes.
RECURRING = [
    ("Alquiler", 480000, "Alquiler", "ICBC", 3),
    ("Expensas", 96000, "Expensas", "ICBC", 5),
    ("Agua", 18000, "Agua", "Galicia", 10),
    ("Luz", 41000, "Luz", "Galicia", 12),
    ("Gas", 22000, "Gas", "Galicia", 12),
    ("TGI", 15000, "TGI", "Galicia", 10),
    ("Flow", 29000, "Flow", "Mercado Pago", 8),
    ("Teléfono", 25000, "Teléfono", "Personal Pay", 15),
    ("Gym", 22000, "Gym", "Mercado Pago", 2),
    ("Obra Social", 35000, "Obra Social", "ICBC", 1),
]


class Command(BaseCommand):
    help = "Crea wallets, categorías, reglas y fijos recurrentes base (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="username; por defecto, el primer superuser")

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("user"))

        wallets_created = 0
        wallets = {}
        for name, kind in WALLETS:
            wallet, created = Wallet.objects.get_or_create(
                owner=user, name=name, defaults={"kind": kind}
            )
            wallets[name] = wallet
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

        # Group the depto's fijos under "Gastos Vivienda" (backfills existing rows too).
        vivienda = categories.get(VIVIENDA_PARENT)
        if vivienda is not None:
            for child_name in VIVIENDA_CHILDREN:
                child = categories.get(child_name)
                if child is not None and child.parent_id != vivienda.id:
                    child.parent = vivienda
                    child.save(update_fields=["parent"])

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

        recurring_created = 0
        for name, amount, cat_name, wallet_name, day in RECURRING:
            category = categories.get(cat_name)
            wallet = wallets.get(wallet_name)
            if category is None or wallet is None:
                continue
            _, created = RecurringExpense.objects.get_or_create(
                owner=user,
                name=name,
                defaults={
                    "default_amount": amount,
                    "category": category,
                    "wallet": wallet,
                    "day_of_month": day,
                },
            )
            recurring_created += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed para '{user}': {wallets_created} wallets, "
                f"{categories_created} categorías, {rules_created} reglas, "
                f"{recurring_created} fijos recurrentes y {assets_created} activos nuevos."
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
