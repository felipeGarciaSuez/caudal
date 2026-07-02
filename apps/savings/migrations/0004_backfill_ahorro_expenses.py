"""Backfill an "Ahorro" expense Transaction for existing wallet-sourced buys.

Before this change, a wallet-sourced dollar buy only discounted the RESTO
SUELDO through a separate calculation (services.saved_ars). Now it's a real
gasto grande instead, so the historical data needs the matching Transaction
or those months would silently lose the deduction.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    SavingsMovement = apps.get_model("savings", "SavingsMovement")
    Category = apps.get_model("transactions", "Category")
    Transaction = apps.get_model("transactions", "Transaction")

    movements = SavingsMovement.objects.filter(
        kind="buy", from_wallet__isnull=False, linked_expense__isnull=True
    ).select_related("asset", "from_wallet")
    for movement in movements:
        category, _ = Category.objects.get_or_create(
            owner=movement.owner,
            name="Ahorro",
            defaults={"kind": "variable", "icon": "piggy-bank"},
        )
        tx = Transaction.objects.create(
            owner=movement.owner,
            date=movement.date,
            period=str(movement.date)[:7],
            amount=movement.ars_amount,
            kind="expense",
            wallet=movement.from_wallet,
            category=category,
            description=f"Compra de dólares ({movement.asset.symbol})",
            is_paid=True,
            source="manual",
        )
        movement.linked_expense = tx
        movement.save(update_fields=["linked_expense"])


def noop_reverse(apps, schema_editor):
    pass  # data migration: nothing to undo, the linked Transactions stay


class Migration(migrations.Migration):
    dependencies = [
        ("savings", "0003_savingsmovement_linked_expense"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
