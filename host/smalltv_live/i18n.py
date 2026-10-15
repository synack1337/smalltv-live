"""Screen labels in the supported languages."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Strings:
    days: tuple[str, ...]
    months: tuple[str, ...]
    session: str
    week: str
    usage_title: str
    no_data: str
    minutes_ago: str      # format string with {n}


STRINGS = {
    "en": Strings(
        days=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
        months=("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        session="Session",
        week="Week",
        usage_title="Claude",
        no_data="no data",
        minutes_ago="{n} min ago",
    ),
    "ro": Strings(
        days=("Lun", "Mar", "Mie", "Joi", "Vin", "Sâm", "Dum"),
        months=("ian", "feb", "mar", "apr", "mai", "iun", "iul", "aug", "sep", "oct", "nov", "dec"),
        session="Sesiune",
        week="Săptămână",
        usage_title="Claude",
        no_data="fără date",
        minutes_ago="acum {n} min",
    ),
}


def strings(language: str) -> Strings:
    return STRINGS[language]
