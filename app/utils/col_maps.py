"""
Column alias maps: DB column name -> possible file header names.
Header comparison is case-insensitive and accent-insensitive.
"""

from __future__ import annotations

import re
import unicodedata


def _norm_header(value: str) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r'[_\-.]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


ARTICULOS_MAP: dict[str, list[str]] = {
    'id_articulo': ['id articulo', 'id_articulo', 'articulo', 'cod articulo', 'codigo articulo'],
    'descripcion': ['descripcion', 'descripcion articulo'],
    'activo': ['activo'],
    'bultos_por_pallet': ['bultos por pallet', 'bultos_por_pallet'],
    'presentacion_bulto': ['presentacion bulto', 'presentacion_bulto'],
    'unidades_por_bulto': ['unidades por bulto', 'unidades_por_bulto'],
    'unidad_medida': ['unidad de medida', 'unidad medida', 'unidad_medida', 'um'],
    'desc_unidad_medida': [
        'descripcion unidad de medida',
        'descripcion unidad medida',
        'desc_unidad_medida',
    ],
    'valor_unidad_medida': ['valor unidad de medida', 'valor unidad medida', 'valor_unidad_medida'],
    'peso': ['peso'],
    'alcoholico': ['alcoholico'],
    'division': ['division'],
    'familia': ['familia'],
    'marca': ['marca'],
    'tipo_producto': ['tipo de producto', 'tipo producto', 'tipo_producto'],
    'unidad_negocio': ['unidad de negocio', 'unidad negocio', 'unidad_negocio'],
    'rotacion_abc': ['rotacion a-b-c', 'rotacion abc', 'rotacion_abc'],
    'grupos_productos': ['grupos de productos', 'grupo de productos', 'grupos_productos'],
    'activo_cc': ['articulos casa central', 'activo cc', 'activo_cc'],
    'activo_dolores': ['articulos sucursal dolores', 'activo dolores', 'activo_dolores'],
    'movil': ['usado en dispositivo movil', 'usado en dispositivo móvil', 'dispositivo movil', 'dispositivo móvil', 'movil', 'móvil'],
    'anulado': ['anulado'],
}


RESUMEN_MAP: dict[str, list[str]] = {
    'sucursal':        ['sucursal'],
    'transporte':      ['transporte'],
    'patente':         ['patente'],
    'carga_maxima_kg': ['carga maxima', 'carga maxima (kg)', 'carga_maxima_kg', 'carga max'],
    'capacidad_up':    ['capacidad up', 'capacidad (up)', 'capacidad_up', 'cap up'],
    'nro_planilla':    ['nro planilla', 'nro_planilla', 'planilla', 'nro. planilla'],
    'fecha_reparto':   ['fecha reparto', 'fecha de reparto', 'fecha_reparto', 'fecha'],
    'pedidos':         ['pedidos', 'pdes'],
    'comprobantes':    ['comprobantes'],
    'bultos_totales':  ['bultos totales', 'bultos_totales', 'total bultos'],
    'um':              ['um', 'u.m.'],
    'pallets':         ['pallets'],
    'unidad_paquete':  ['unidad paquete', 'unidad_paquete', 'up'],
    'peso_carga':      ['peso carga', 'peso_carga', 'peso total'],
    'importe_total':   ['importe total', 'importe_total', 'total importe'],
    'picking':         ['picking'],
    'fecha_llegada':   ['fecha llegada', 'fecha de llegada', 'fecha_llegada'],
    'fecha_salida':    ['fecha salida', 'fecha de salida', 'fecha_salida'],
}


DETALLE_MAP: dict[str, list[str]] = {
    'sucursal':               ['sucursal'],
    'comprobante':            ['comprobante'],
    'fecha_comprobante':      [
        'fecha comprobante',
        'fecha de entrega comprobante',
        'fecha de entrega comp',
        'fecha entrega comp',
        'fecha_comprobante',
    ],
    'id_cliente':             ['id cliente', 'id_cliente', 'cod cliente', 'codigo cliente', 'cliente'],
    'nombre_cliente':         ['nombre cliente', 'nombre_cliente', 'razon social', 'cliente'],
    'domicilio':              ['domicilio'],
    'localidad':              ['localidad'],
    'estado':                 ['estado'],
    'nro_planilla':           ['nro planilla', 'nro de planilla', 'nro_planilla', 'planilla', 'nro. planilla'],
    'transporte':             ['transporte'],
    'chofer':                 ['chofer'],
    'patente':                ['patente'],
    'fecha_entrega_planilla': [
        'fecha entrega planilla',
        'fecha de entrega planilla',
        'fecha de entrega plantilla',
        'fecha_entrega_planilla',
        'fecha entrega',
        'fecha',
    ],
    'id_articulo':            ['id articulo', 'id_articulo', 'cod articulo', 'codigo articulo', 'articulo'],
    'descripcion_articulo':   ['descripcion articulo', 'descripcion_articulo', 'descripcion', 'articulo'],
    'bultos':                 ['bultos'],
    'unidad_medida':          ['unidad medida', 'un medida', 'unidad_medida'],
    'cantidad_um':            [
        'cantidad um', 'cantidad_um', 'cant um', 'cant. um',
        'cantidad u.m.', 'cantidad um.', 'um', 'u.m.',
        'hectolitros', 'hl', 'litros',
        'cantidad',
    ],
    'tipo_entrega':           ['tipo entrega', 'tipo de entrega', 'tipo_entrega', 'tipo'],
    'deposito':               ['deposito'],
    'propio':                 ['propio'],
    'nro_pedido':             ['nro pedido', 'nro_pedido', 'pedido', 'nro. pedido'],
    'cantidad_up':            ['cantidad up', 'cantidad (up)', 'cantidad_up', 'cant up'],
    'importe':                ['importe'],
    'peso':                   ['peso'],
    'hora_entrega':           ['hora entrega', 'hora de entrega', 'hora_entrega', 'hora'],
    'motivo_rechazo':         ['motivo rechazo', 'motivo de rechazo', 'motivo_rechazo', 'mot de rechazo', 'motivo'],
    'ruta_venta':             ['ruta venta', 'ruta de venta', 'ruta_venta'],
    'ruta_distribucion':      ['ruta distribucion', 'ruta de distribucion', 'ruta_distribucion', 'ruta dist'],
}

CLIENTES_MAP: dict[str, list[str]] = {
    'cliente': ['cliente', 'cod cliente', 'codigo cliente', 'id cliente'],
    'descripcion': ['descripcion', 'desc', 'tipo cliente', 'segmento cliente'],
    'sucursal': ['sucursal'],
    'razon_social': ['razon social', 'razon_social', 'razon'],
    'nombre_fantasia': ['nombre de fantasia', 'nombre fantasia', 'nombre de fantasía', 'fantasia'],
    'telefonos': ['telefonos', 'telefono', 'teléfonos', 'tel'],
    'movil': ['movil', 'móvil', 'celular'],
    'email': ['e-mail', 'email', 'mail'],
    'domicilio': ['domicilio'],
    'calle': ['calle'],
    'altura': ['altura'],
    'depto': ['depto', 'departamento'],
    'calle_1': ['calle 1', 'calle_1'],
    'calle_2': ['calle 2', 'calle_2'],
    'comentario': ['comentario'],
    'coord_x': ['coord x', 'coord_x', 'coordenada x', 'coordenada_x'],
    'coord_y': ['coord y', 'coord_y', 'coordenada y', 'coordenada_y'],
    'lugar_entrega': ['lugar de entrega', 'lugar_entrega'],
    'calle_entrega': ['calle de entrega', 'calle_entrega'],
    'altura_entrega': ['altura de entrega', 'altura_entrega'],
    'depto_entrega': ['depto de entrega', 'depto_entrega'],
    'calle_1_entrega': ['calle 1 de entrega', 'calle_1_de_entrega', 'calle_1_entrega'],
    'calle_2_entrega': ['calle 2 de entrega', 'calle_2_de_entrega', 'calle_2_entrega'],
    'comentario_entrega': ['comentario de entrega'],
    'horario_entrega': ['horario de entrega', 'horario_entrega'],
    'flete_entrega': ['flete de entrega', 'flete_entrega'],
    'coord_x_entrega': ['coord x de entrega', 'coord_x_de_entrega', 'coord_x_entrega'],
    'coord_y_entrega': ['coord y de entrega', 'coord_y_de_entrega', 'coord_y_entrega'],
    'localidad': ['descripcion localidad', 'localidad'],
    'provincia': ['descripcion provincia', 'provincia'],
    'departamento': ['descripcion departamento', 'departamento'],
    'area': ['area', 'área'],
    'subcanal': ['subcanal'],
    'ramo': ['ramo'],
    'lista_precio': ['lista de precios', 'lista de precio', 'lista_precio'],
    'hereda': ['hereda'],
    'lista_boni': ['lista de bonificaciones', 'lista de boni', 'lista de bonificacion', 'lista_boni'],
    'forma_pago': ['forma de pago', 'forma_pago'],
    'plazo_pago': ['plazo de pago', 'plazo_pago'],
    'limite_cr_anticipo': ['limite cr anticipo', 'limite_cr_anticipo'],
    'categoria': ['categoria'],
    'apellido_paterno': ['apellido paterno', 'apellido_paterno'],
    'apellido_materno': ['apellido materno', 'apellido_materno'],
    'nombres': ['nombres'],
    'tipo_identif': ['tipo identif', 'tipo de identif', 'tipo identificacion', 'tipo_identif'],
    'identificador': ['identificador', 'identificacion'],
    'fecha_vencimiento': ['vencimiento cuit', 'fecha vencimiento', 'fecha_vencimiento'],
    'exento_ib': ['exento ib', 'exento_ib'],
    'inscripto_ib': ['inscripto ib', 'inscripto_ib'],
    'convenio_mut': ['convenio multilateral', 'convenio mu', 'convenio_mut'],
    'agente_de_pe': ['agente de percepcion', 'agente de pe', 'agente_de_pe'],
    'documento': ['documento! por defecto', 'documento por defecto', 'documento', 'documento!'],
    'licencia_alco': ['licencia alcohol', 'licencia alco', 'licencia_alco'],
    'vencimiento': ['vencimiento licencia alcohol', 'vencimiento'],
    'alta_fecha': ['alta fecha', 'alta_fecha'],
    'anulado': ['anulado'],
    'anulado_fecha': ['anulado fecha', 'anulado_fecha'],
    'modificacion': ['modificacion fecha', 'modificacion'],
    'cliente_asoc': ['cliente asociado', 'cliente asoci', 'cliente_asoc'],
    'cta_y_ord': ['cta y orden', 'cta. y ord', 'cta y ord', 'cta_y_ord'],
    'fuerza_venta_1_dias_visita': [
        'fuerza de venta 1 dias de visita',
        'fuerza de venta 1 dias visita',
        'fuerza venta 1 dias de visita',
        'fuerza venta 1 dias visita',
        'dias de visita',
        'dias visita',
    ],
}

RECHAZOS_MAP: dict[str, list[str]] = {
    'motivo_rechazo': ['motivo rechazo', 'motivo de rechazo', 'motivo_rechazo', 'motivo', 'rechazo', 'descripcion'],
    'sector': ['sector', 'area', 'área'],
    'tomar': ['tomar', 'tomar?', 'incluir', 'incluir?', 'cuenta', 'cuenta rechazo'],
}


def map_headers(headers: list[str], mapping: dict[str, list[str]]) -> dict[str, int]:
    """Return {db_col: column_index} for the given header row."""
    hl: dict[str, int] = {}
    for i, header in enumerate(headers):
        hl.setdefault(_norm_header(header), i)
    result: dict[str, int] = {}
    for col, aliases in mapping.items():
        for alias in aliases:
            key = _norm_header(alias)
            if key in hl:
                result[col] = hl[key]
                break
    return result
