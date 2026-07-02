from django.contrib.auth.decorators import login_required
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.dashboard.templatetags.icons import ICONS

from .models import Category

# Icons offered in the picker (the whole set, minus the neutral fallback).
ICON_CHOICES = sorted(name for name in ICONS if name != "tag")


def _current_period() -> str:
    return timezone.localdate().strftime("%Y-%m")


def _categories_context(user, **extra) -> dict:
    categories = (
        Category.objects.filter(owner=user)
        .select_related("parent")
        .annotate(child_count=Count("children"))
        .order_by("kind", "name")
    )
    ctx = {
        "categories": categories,
        # Only top-level categories can be chosen as a group (one nesting level).
        "parent_options": Category.objects.filter(owner=user, parent__isnull=True).order_by("name"),
        "kinds": Category.Kind.choices,
        "icon_choices": ICON_CHOICES,
        "nav_active": "month",
        "add_href": reverse("dashboard:month", args=[_current_period()]) + "#add-card",
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
    """Validate fields shared by add/update. Returns (data, error)."""
    name = (request.POST.get("name") or "").strip()
    if not name:
        return None, "Poné un nombre para la categoría."
    dupe = Category.objects.filter(owner=user, name__iexact=name)
    if instance is not None:
        dupe = dupe.exclude(pk=instance.pk)
    if dupe.exists():
        return None, f"Ya tenés una categoría llamada {name}."
    kind = request.POST.get("kind")
    if kind not in Category.Kind.values:
        return None, "Elegí un tipo (fijo, variable u hormiga)."
    icon = (request.POST.get("icon") or "").strip()
    if icon and icon not in ICONS:
        icon = ""

    parent = None
    parent_id = request.POST.get("parent")
    if parent_id:
        parent = Category.objects.filter(owner=user, pk=parent_id).first()
        if parent is None:
            return None, "El grupo elegido no existe."
        if instance is not None and parent.pk == instance.pk:
            return None, "Una categoría no puede agruparse en sí misma."
        if parent.parent_id is not None:
            return None, "Elegí un grupo de primer nivel (no una subcategoría)."

    data = {"name": name, "kind": kind, "icon": icon, "parent": parent}
    return data, None


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
    # A category that groups others can't itself be nested (would be two levels).
    if data["parent"] is not None and category.children.exists():
        return _error_body(request, "Esta categoría es un grupo: no la podés meter en otro grupo.")
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
