"""Una única definición del día de emisión del pronóstico."""

from datetime import date
from zoneinfo import ZoneInfo

from reposicion.source_io import parse_instant

TIMEZONE = "America/Guatemala"


def validate_origin(origin, issued_at):
    day = date.fromisoformat(origin)
    local_day = parse_instant(issued_at).astimezone(ZoneInfo(TIMEZONE)).date()
    if day != local_day:
        raise ValueError(
            f"Origen {day} incompatible con emisión: fecha en {TIMEZONE}={local_day}. Indicar un corte histórico coherente."
        )
    return day
