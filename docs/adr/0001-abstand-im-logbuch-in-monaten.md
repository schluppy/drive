# 0001 – Abstand zwischen Logbucheinträgen: ab 90 Tagen in Monaten

Stand: 2026-11-20 · Status: angenommen

## Kontext

Die Logbuch-Liste zeigt bei jedem Eintrag die Tage seit dem vorigen Eintrag derselben Kategorie
(Tankfüllungen: desselben Kraftstoffs; Fahrten ausgenommen). Große Werte wie „444 Tage“ lassen sich
schlecht erfassen.

## Entscheidung

- Bis einschließlich 90 Tage steht die Zahl in Tagen („28 Tage“, „1 Tag“).
- Bei mehr als 90 Tagen steht sie in Monaten („3 Monate“).
- Ein Monat hat dabei immer 30 Tage, kein Kalendermonat.
- Gerundet wird auf ganze Monate, kaufmännisch (ab 15 Resttagen auf, sonst ab):
  `(tage + 15) // 30`. Beispiele: 101 → 3 Monate, 105 → 4 Monate, 444 → 15 Monate.
- Da 91 Tage schon 3 Monate ergibt, kommt „1 Monat“ nie vor; die Einheit ist immer „Monate“.

## Folgen

- Umsetzung: Filter `abstand` in `portal/templatetags/drive.py`, Test in `tests/test_seiten.py`.
- Die Anzeige ist bewusst ungenau; genaue Tage stehen an den Einträgen (Datum) selbst.
- Wird die Schwelle oder die Monatslänge geändert, diese Entscheidung ersetzen statt still anpassen.
