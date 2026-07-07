"""Load a full example month into a user so the dashboard looks alive.

For demo/test accounts (e.g. the public "prueba" users). Populates: sueldo,
fixed expenses (some already paid), hormiga spend, a couple of big expenses, two
dollar purchases (patrimonio) and a credit-card statement to review.

Idempotent: it first clears the user's transactions/savings/budget so re-running
always yields the same demo month. Meant for throwaway demo users, not real data.

Usage:
    uv run python manage.py seed_demo prueba1
"""

import calendar
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.budgets.models import MonthlyBudget, RecurringExpense
from apps.budgets.services import ensure_month_fixed
from apps.savings import services as savings_services
from apps.savings.models import Asset, SavingsMovement
from apps.transactions.models import Category, Transaction
from apps.wallets.models import CardStatement, Wallet

User = get_user_model()

SUELDO = Decimal("2500000")
DOLLAR_PRICE = Decimal("1450")

# (recurring name, category, wallet, amount, day_of_month, already_paid)
FIJOS = [
    ("Alquiler", "Vivienda", "ICBC", "600000", 1, True),
    ("Expensas", "Vivienda", "Galicia", "80000", 5, True),
    ("Flow", "Servicios", "Mercado Pago", "29000", 8, True),
    ("Gym", "Salud", "Mercado Pago", "60000", 2, True),
    ("TGI", "Impuestos", "Efectivo", "50000", 10, False),
]

# Small, below the hormiga threshold -> hormiga panel. (desc, category, wallet, amount, day)
HORMIGAS = [
    ("Café mañanero", "Café", "Efectivo", "3500", 3),
    ("Café con Juan", "Café", "Efectivo", "4200", 12),
    ("PedidosYa", "Delivery", "Mercado Pago", "8600", 6),
    ("Rappi noche", "Delivery", "Personal Pay", "9400", 19),
    ("Uber viernes", "Transporte/Uber", "Personal Pay", "4300", 9),
    ("Kiosco esquina", "Kiosco", "Efectivo", "1800", 14),
    ("Compra en app", "Apps", "Ualá", "3200", 7),
    ("Cargador USB", "Compras chicas", "Mercado Pago", "6500", 21),
]

# Big variable spend (>= threshold) -> gastos grandes. (desc, category, wallet, amount, day)
GRANDES = [
    ("Carrefour compra grande", "Supermercado", "Galicia", "125000", 15),
    ("Nafta full", "Nafta", "ICBC", "110000", 11),
]

# Two dollar purchases. (asset symbol, quantity, ars_amount, from_wallet, location, day)
COMPRAS_DOLARES = [
    ("USDT", "100", "145000", "Mercado Pago", "Binance", 4),
    ("USD", "100", "145000", "Efectivo", "Colchón", 16),
]

# Credit-card charges left "sin revisar" on ICBC Visa.
# (desc, amount, day, installment_current, installment_total)
CARD = [
    ("GOOGLE *Google Play", "2826", 6, None, None),
    ("LA BODEGUITA", "11513", 12, None, None),
    ("COTO SUCURSAL 97", "140040", 18, 1, 3),
]


class Command(BaseCommand):
    help = "Carga un mes de ejemplo en un usuario (para cuentas demo). Resetea sus datos."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Usuario a poblar (idealmente una cuenta de prueba).")

    @db_transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"No existe el usuario '{username}'.") from exc

        # Ensure base wallets/categories/assets exist, then start from a clean slate.
        call_command("seed_data", user=username, verbosity=0)
        SavingsMovement.objects.filter(owner=user).delete()
        Transaction.objects.filter(owner=user).delete()
        CardStatement.objects.filter(owner=user).delete()
        RecurringExpense.objects.filter(owner=user).delete()
        MonthlyBudget.objects.filter(owner=user).delete()

        period = timezone.localdate().strftime("%Y-%m")
        wallets = {w.name: w for w in Wallet.objects.filter(owner=user)}
        cats = {c.name: c for c in Category.objects.filter(owner=user)}

        def day(d: int) -> date:
            year, month = (int(p) for p in period.split("-"))
            last = calendar.monthrange(year, month)[1]
            return date(year, month, min(d, last))

        MonthlyBudget.objects.create(owner=user, period=period, expected_income=SUELDO)

        # Fixed expenses: create templates, generate this month's checklist, pay some.
        paid_templates = []
        for name, cat, wallet, amount, dom, is_paid in FIJOS:
            tmpl = RecurringExpense.objects.create(
                owner=user,
                name=name,
                default_amount=Decimal(amount),
                category=cats[cat],
                wallet=wallets[wallet],
                day_of_month=dom,
            )
            if is_paid:
                paid_templates.append(tmpl.id)
        ensure_month_fixed(user, period)
        Transaction.objects.filter(
            owner=user, period=period, recurring_expense_id__in=paid_templates
        ).update(is_paid=True)

        # Hormiga + big variable spend.
        for desc, cat, wallet, amount, dom in HORMIGAS + GRANDES:
            Transaction.objects.create(
                owner=user,
                date=day(dom),
                amount=Decimal(amount),
                kind=Transaction.Kind.EXPENSE,
                wallet=wallets[wallet],
                category=cats[cat],
                description=desc,
                is_paid=True,
                source=Transaction.Source.MANUAL,
            )

        # Savings: set a manual dollar quote, then record the purchases (each buy
        # also creates its "Ahorro" gasto grande, same path as the app's UI).
        savings_services.set_dollar_price(DOLLAR_PRICE)
        for symbol, qty, ars, wallet, location, dom in COMPRAS_DOLARES:
            asset = Asset.objects.get(symbol=symbol)
            quantity = Decimal(qty)
            ars_amount = Decimal(ars)
            movement = SavingsMovement.objects.create(
                owner=user,
                date=day(dom),
                kind=SavingsMovement.Kind.BUY,
                asset=asset,
                quantity=quantity,
                price=(ars_amount / quantity).quantize(Decimal("0.01")),
                ars_amount=ars_amount,
                from_wallet=wallets[wallet],
                location=location,
            )
            savings_services.create_ahorro_expense(movement)

        # Credit-card charges left to review (form the "resumen de tarjeta").
        card = wallets["ICBC Visa"]
        for desc, amount, dom, cur, total in CARD:
            Transaction.objects.create(
                owner=user,
                date=day(dom),
                amount=Decimal(amount),
                kind=Transaction.Kind.EXPENSE,
                wallet=card,
                category=None,
                description=desc,
                is_paid=True,
                source=Transaction.Source.IMPORT,
                needs_review=True,
                installments_current=cur,
                installments_total=total,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo cargado para '{username}' en {period}: sueldo, "
                f"{len(FIJOS)} fijos, {len(HORMIGAS)} hormigas, {len(GRANDES)} grandes, "
                f"{len(COMPRAS_DOLARES)} compras de dólares y {len(CARD)} consumos de tarjeta."
            )
        )
