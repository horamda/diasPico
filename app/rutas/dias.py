"""Conversión de días de entrega entre formatos.

Formato interno: string con códigos de 2 letras en orden fijo, ej. "MAVI", "LUJU", "" (sin días).
ChessERP (eClifuerza.diasEntrega): "3,6" con 1 = domingo, 2 = lunes ... 7 = sábado.
Excel de ERP (Fuerza de venta 1 Dias de entrega): "MAR,VIE".
BEES: columnas Mon..Sun con FREE / NO.
"""
DIAS = ["LU", "MA", "MI", "JU", "VI", "SA"]
NOMBRES = {"LU": "Lunes", "MA": "Martes", "MI": "Miércoles", "JU": "Jueves", "VI": "Viernes", "SA": "Sábado"}
BEES_COLS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_CHESS_NUM = {2: "LU", 3: "MA", 4: "MI", 5: "JU", 6: "VI", 7: "SA"}
_CHESS_INV = {v: k for k, v in _CHESS_NUM.items()}
_TXT = {"LUN": "LU", "MAR": "MA", "MIE": "MI", "MIÉ": "MI", "JUE": "JU", "VIE": "VI", "SAB": "SA", "SÁB": "SA"}


def normalizar(dias) -> str:
    """Acepta 'MAVI', 'MA,VI', ['MA','VI'] y devuelve 'MAVI' ordenado; ignora basura."""
    if not dias:
        return ""
    if isinstance(dias, str):
        s = dias.upper().replace(",", "").replace(" ", "")
        partes = [s[i:i + 2] for i in range(0, len(s), 2)]
    else:
        partes = [str(p).upper() for p in dias]
    return "".join(d for d in DIAS if d in partes)


def desde_visita(valor) -> str:
    """Días de visita del maestro ('MAR,VIE', 'DOM') -> 'MAVI', 'DO'. Son días del vendedor, no de entrega."""
    partes = {_TXT.get(p.strip().upper(), "DO" if p.strip().upper() == "DOM" else "") for p in str(valor or "").split(",")}
    return "".join(d for d in DIAS + ["DO"] if d in partes)


def desde_chess(valor: str) -> str:
    if not valor:
        return ""
    nums = []
    for p in str(valor).split(","):
        p = p.strip()
        if p.isdigit():
            nums.append(int(p))
    return "".join(d for d in DIAS if _CHESS_INV[d] in nums)


def a_chess(dias: str) -> str:
    return ",".join(str(_CHESS_INV[d]) for d in DIAS if d in normalizar(dias))


def desde_texto_erp(valor) -> str:
    if not valor or not isinstance(valor, str):
        return ""
    cods = [_TXT.get(p.strip().upper(), "") for p in valor.split(",")]
    return "".join(d for d in DIAS if d in cods)


def lista(dias: str):
    d = normalizar(dias)
    return [d[i:i + 2] for i in range(0, len(d), 2)]


def a_bees(dias: str):
    """Devuelve 7 valores FREE/NO para Mon..Sun (domingo siempre NO)."""
    d = normalizar(dias)
    return [("FREE" if c in d else "NO") for c in DIAS] + ["NO"]
