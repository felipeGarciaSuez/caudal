from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.dashboard.templatetags.icons import ICONS

from .models import Category

# Icons offered in the picker (the whole set, minus the neutral fallback).
ICON_CHOICES = sorted(name for name in ICONS if name != "tag")


def _categories_context(user, **extra) -> dict:
    ctx = {
        "categories": Category.objects.filter(owner=user).order_by("name"),
        "icon_choices": ICON_CHOICES,
        "nav_active": "settings",
    }
    ctx.update(extra)
    return ctx


@login_required
def categories_home(request):
    return render(request, "transactions/categories.html", _categories_context(request.user))


def _error_body(request, message: str):
    context = _categories_context(request.user)
    context["form_error"] = message
    return render(request, "transactions/_categories_body.html", context, status=400)


def _clean_common(request, user, instance=None):
    """Validate a category's fields (name + icon). Returns (data, error)."""
    name = (request.POST.get("name") or "").strip()
    if not name:
        return None, "Poné un nombre para la categoría."
    dupe = Category.objects.filter(owner=user, name__iexact=name)
    if instance is not None:
        dupe = dupe.exclude(pk=instance.pk)
    if dupe.exists():
        return None, f"Ya tenés una categoría llamada {name}."
    icon = (request.POST.get("icon") or "").strip()
    if icon and icon not in ICONS:
        icon = ""
    return {"name": name, "icon": icon}, None


@login_required
@require_POST
def add_category(request):
    data, error = _clean_common(request, request.user)
    if error:
        return _error_body(request, error)
    Category.objects.create(owner=request.user, **data)
    context = _categories_context(request.user, just_saved=True)
    return render(request, "transactions/_categories_body.html", context)


@login_required
@require_POST
def update_category(request, pk):
    category = get_object_or_404(Category, pk=pk, owner=request.user)
    data, error = _clean_common(request, request.user, instance=category)
    if error:
        return _error_body(request, error)
    for field, value in data.items():
        setattr(category, field, value)
    category.save()
    context = _categories_context(request.user, just_saved=True)
    return render(request, "transactions/_categories_body.html", context)


@login_required
@require_POST
def delete_category(request, pk):
    category = get_object_or_404(Category, pk=pk, owner=request.user)
    try:
        category.delete()
    except ProtectedError:
        # A fixed template points at it (RecurringExpense.category is PROTECT).
        # Its movements would just go uncategorized (SET_NULL), but a recurring
        # rule can't be left dangling, so block and tell the user.
        return _error_body(
            request,
            f"No podés borrar {category.name}: la usa un gasto fijo. Cambialo primero.",
        )
    context = _categories_context(request.user)
    return render(request, "transactions/_categories_body.html", context)
