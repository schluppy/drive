"""Fahrzeuge der Familie für die Auswahl im Kopf jeder Seite."""


def fahrzeugauswahl(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or user.familie_id is None:
        return {}
    from fahrzeuge.models import Fahrzeug
    fahrzeuge = list(Fahrzeug.objects.filter(familie_id=user.familie_id).select_related("halter"))
    aktiv = None
    kwargs = getattr(request.resolver_match, "kwargs", {}) or {}
    fid = kwargs.get("fahrzeug_id") or request.session.get("fahrzeug")
    if fid:
        aktiv = next((f for f in fahrzeuge if f.pk == int(fid)), None)
    if aktiv is None:
        aktiv = next((f for f in fahrzeuge if not f.verkauft and f.halter_id == user.pk), None) \
            or next((f for f in fahrzeuge if not f.verkauft), None)
    return {"alle_fahrzeuge": fahrzeuge, "aktuelles_fahrzeug": aktiv}
