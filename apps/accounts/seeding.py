"""Base seed data for a Caudal user: wallets, categories, auto-categorization
rules and global savings assets.

Single source of truth. Used both by the ``seed_data`` management command
(manual/explicit) and by the post_save signal that seeds a freshly created user
automatically (see apps/accounts/signals.py).

Everything is idempotent (get_or_create), so running it more than once is safe.
The seed is only a starting point: every wallet, category and rule is
editable/removable from the app.
"""

from apps.imports.models import CategoryRule
from apps.savings.models import Asset
from apps.transactions.models import Category
from apps.wallets.models import Wallet

# Base wallets every user starts with. Kept deliberately generic: Mercado Pago
# and cash are near-universal here. Banks and credit cards are personal (ICBC,
# Galicia, card statements...), so the user adds their own from the app.
WALLETS = [
    ("Mercado Pago", Wallet.Kind.WALLET),
    ("Efectivo", Wallet.Kind.CASH),
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


def seed_wallets(user):
    """Create the base wallets for ``user``. Returns how many were new."""
    created = 0
    for name, kind in WALLETS:
        _, was_created = Wallet.objects.get_or_create(
            owner=user, name=name, defaults={"kind": kind}
        )
        created += int(was_created)
    return created


def seed_categories(user):
    """Create the base categories for ``user``.

    Returns ``(categories_by_name, created_count)``; the map is reused to wire
    up the auto-categorization rules.
    """
    created = 0
    categories = {}
    for name, kind, icon in CATEGORIES:
        cat, was_created = Category.objects.get_or_create(
            owner=user, name=name, defaults={"kind": kind, "icon": icon}
        )
        # Keep the icon in sync (e.g. migrating older emoji icons to Lucide names).
        if not was_created and cat.icon != icon:
            cat.icon = icon
            cat.save(update_fields=["icon"])
        categories[name] = cat
        created += int(was_created)
    return categories, created


def seed_rules(user, categories):
    """Create the keyword rules for ``user`` given its categories map."""
    created = 0
    for priority, (keyword, cat_name) in enumerate(RULES, start=1):
        category = categories.get(cat_name)
        if category is None:
            continue
        _, was_created = CategoryRule.objects.get_or_create(
            owner=user,
            keyword=keyword,
            category=category,
            defaults={"priority": priority},
        )
        created += int(was_created)
    return created


def seed_assets():
    """Create the global savings assets (not per-user). Returns how many were new."""
    created = 0
    for symbol, name, kind in ASSETS:
        _, was_created = Asset.objects.get_or_create(
            symbol=symbol, defaults={"name": name, "kind": kind}
        )
        created += int(was_created)
    return created


def seed_user(user):
    """Seed all base data for ``user`` (wallets, categories, rules, assets).

    Idempotent. Returns a dict with the count of newly created rows per kind.
    """
    wallets = seed_wallets(user)
    categories, categories_created = seed_categories(user)
    rules = seed_rules(user, categories)
    assets = seed_assets()
    return {
        "wallets": wallets,
        "categories": categories_created,
        "rules": rules,
        "assets": assets,
    }
