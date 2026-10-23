"""Verwaltung nur für den Super-Admin: Familien und Personen.

Fahrzeuge und Logbücher werden in der eigenen Oberfläche bearbeitet, nicht hier –
so sieht auch der Super-Admin keine Daten fremder Familien.
"""
from django import forms
from django.contrib import admin

from .models import Familie, Person


class NurSuperAdmin:
    def _erlaubt(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_module_permission(self, request):
        return self._erlaubt(request)

    def has_view_permission(self, request, obj=None):
        return self._erlaubt(request)

    def has_add_permission(self, request, *args):
        return self._erlaubt(request)

    def has_change_permission(self, request, obj=None):
        return self._erlaubt(request)

    def has_delete_permission(self, request, obj=None):
        return self._erlaubt(request)


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["name", "email", "familie", "farbe", "erinnerungen_per_mail", "is_active", "is_superuser"]
        labels = {"is_superuser": "Super-Admin"}
        help_texts = {"is_superuser": "legt Familien und Personen an (Verwaltung)"}


@admin.register(Person)
class PersonAdmin(NurSuperAdmin, admin.ModelAdmin):
    form = PersonForm
    list_display = ["name", "email", "familie", "is_active", "is_superuser", "zuletzt_aktiv"]
    list_filter = ["familie", "is_active", "is_superuser"]
    search_fields = ["name", "email"]

    def save_model(self, request, obj, form, change):
        obj.is_staff = obj.is_superuser   # nur der Super-Admin braucht die Verwaltung
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)


class PersonInline(admin.TabularInline):
    model = Person
    fields = ["name", "email", "is_active"]
    readonly_fields = ["name", "email", "is_active"]
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Familie)
class FamilieAdmin(NurSuperAdmin, admin.ModelAdmin):
    list_display = ["name", "anzahl_personen", "anzahl_fahrzeuge", "angelegt_am"]
    search_fields = ["name"]
    fields = ["name"]
    inlines = [PersonInline]

    @admin.display(description="Personen")
    def anzahl_personen(self, obj):
        return obj.personen.count()

    @admin.display(description="Fahrzeuge")
    def anzahl_fahrzeuge(self, obj):
        return obj.fahrzeuge.count()
