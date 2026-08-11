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
    if isinstance(v, (int, float)):
        return float(v)
    text = str(v).strip()
    if not text:
        return None
    text = text.replace('\xa0', '').replace(' ', '')
    text = text.replace('$', '').replace('%', '')
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1]
    if text.startswith('+'):
        text = text[1:]

    comma = text.rfind(',')
    dot = text.rfind('.')
    if comma >= 0 and dot >= 0:
        if comma > dot:
            # Formato regional: 1.234,56
            text = text.replace('.', '').replace(',', '.')
        else:
            # Formato US: 1,234.56
            text = text.replace(',', '')
    elif comma >= 0:
        parts = text.split(',')
        if len(parts[-1]) == 3 and len(parts) > 1:
            # 1,234 o 12,345,678 como miles.
            text = ''.join(parts)
        else:
            text = text.replace(',', '.')
    elif dot >= 0:
        parts = text.split('.')
        if len(parts[-1]) == 3 and len(parts) > 1:
            # 1.234 o 12.345.678 como miles.
            text = ''.join(parts)
    try:
        value = float(text)
        return -value if negative else value
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
