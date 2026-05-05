# core/categories.py
# Kategorien für Data Collection.
# Jede Kategorie hat eine id, einen Namen, und eine Liste von Feldern.
#
# Field-Typen:
#   "date"          – Datum, navigierbar mit Pfeiltasten
#   "smiley_scale"  – 5 Smileys, Auswahl mit Pfeiltasten + Enter
#   "text"          – Freitext (noch nicht implementiert)

CATEGORIES = [
    {
        "id": "sleep_quality",
        "name": "Sleep Quality",
        "fields": [
            {
                "id": "date",
                "label": "Date",
                "type": "date",
            },
            {
                "id": "quality",
                "label": "Sleep Quality",
                "type": "smiley_scale",
                "steps": 5,
            },
        ],
    },
    {
        "id": "food_intake",
        "name": "Food Intake",
        "fields": [
            {
                "id": "date",
                "label": "Date",
                "type": "date",
            },
            {
                "id": "meal",
                "label": "Meal",
                "type": "text",
            },
        ],
    },
]
