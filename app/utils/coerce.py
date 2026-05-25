from datetime import date, datetime


def to_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(str(v).strip(), fmt).date()
        except ValueError:
            pass
    return None


def to_dec(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(',', '.').replace(' ', ''))
    except (ValueError, TypeError):
        return None


def to_int(v) -> int | None:
    try:
        return int(float(str(v).replace(',', '.')))
    except (ValueError, TypeError):
        return None


def to_time(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.time()
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(str(v).strip(), fmt).time()
        except ValueError:
            pass
    return None


def norm_fecha(raw: str) -> str | None:
    """Normalize a date string to YYYY-MM-DD. Returns None if unparseable."""
    d = to_date(raw)
    return d.isoformat() if d else None
