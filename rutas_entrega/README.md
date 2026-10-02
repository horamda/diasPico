# Rutas de Entrega: módulo Flask

Mapa de clientes por localidad y día de entrega, plan de recorridos por camión, alertas (sin días, sin geolocalizar, ubicación dudosa) y exportación del archivo de días para BEES.

Viene como **Blueprint** con prefijo de tablas `rt_`, así que se suma a una app Flask existente sin chocar con lo que ya tiene. También corre solo con `app.py`.

Requiere Python 3.10 o superior y PostgreSQL. SQLite también funciona para pruebas.

---

## 1. Sumarlo a otra app Flask

1. Copiá la carpeta `rutas/` a la raíz de tu proyecto, al lado de tu `app.py`.
2. Sumá a tu `requirements.txt` lo que falte: `SQLAlchemy>=2.0`, `psycopg2-binary`, `requests`, `openpyxl`.
3. En tu app:

```python
from rutas import init_rutas

app = Flask(__name__)
# ... tu config ...
init_rutas(app)                       # queda en /rutas  (mapa)  y /rutas/plan
# init_rutas(app, url_prefix="/logistica/rutas")   # si querés otro prefijo
```

**Base de datos.** El módulo usa la misma base que tu app: lee `SQLALCHEMY_DATABASE_URI` o, si no está, `DATABASE_URL`. Para usar otra base, definí `RUTAS_DATABASE_URL`. Las tablas `rt_*` se crean solas al arrancar. Para desactivarlo: `RUTAS_CREATE_TABLES = False`, y en ese caso usá `schema.sql` o `flask rutas init-db`.

**Login.** Si tu app usa Flask-Login:

```python
from flask_login import login_required, current_user
app.config["RUTAS_LOGIN_REQUIRED"] = login_required
app.config["RUTAS_USUARIO"] = lambda: current_user.username   # queda en el historial de cambios
```

## 2. Cargar los datos (una vez)

```bash
flask rutas seed                                   # depósitos, localidad→sucursal, vehículos y plan de la hoja INFORME
flask rutas import-excel "ARMADO DE DIAS DE ENTREGA - Dolores 30.09.26.xlsm"
```

`import-excel` lee tres hojas del libro:

- **CLIENTES** (sucursal 2): pasa a `rt_cliente`.
- **LOCALIDAD-SUCURSAL**: pasa a `rt_localidad`.
- **RUTAS DE ENTREGA**: los días de cada cliente pasan a `rt_cliente_entrega`.

Si lo corrés de nuevo, no pisa los días que ya editaste en la app. Para forzarlo, agregá `--pisar-dias`.

> En la hoja RUTAS DE ENTREGA las columnas LAT y LONG vienen invertidas. Por eso las coordenadas se toman de la hoja CLIENTES (las del ERP).

## 3. Sincronización con ChessERP

```bash
flask rutas sync-chess                 # usa CHESS_SUCURSALES (default 2)
flask rutas sync-chess --sucursal 2 --dias-desde-erp
```

- Actualiza **solo** `rt_cliente` (el espejo del ERP): razón social, domicilio, coordenadas, anulado y días del ERP.
- **Nunca** pisa lo que se armó en la app (`rt_cliente_entrega`).
- A los clientes nuevos les crea la fila de entrega vacía. Así aparecen como "sin días" hasta que alguien les asigne días. Con `--dias-desde-erp`, en cambio, arrancan con los días que tienen en el ERP.

**Ajuste necesario.** El parseo de clientes está validado contra una respuesta real de la API: `Clientes.eClientes[]` con `eClialias[]`, y `eClifuerza[]` donde la fila vigente es la que tiene `fechaFinFuerza = 9999-12-31` y `diasEntrega = "3,6"` (1 = domingo). El **login**, en cambio, no está probado. En `rutas/chess.py`, `ChessClient.login()` hace un POST a `CHESS_LOGIN_PATH` con usuario y contraseña. Reemplazá ese método por el login de dos pasos que ya tenés en tu MCP de ChessERP, y ajustá `CHESS_CLIENTES_PATH` y el nombre del parámetro de lote (`nroLote`) si tu API usa otros.

**Sync automática (cron de Railway):**

```bash
curl -X POST https://tu-app/rutas/api/sync -H "X-Sync-Token: $RUTAS_SYNC_TOKEN"
```

## 4. Pantallas

| Ruta | Qué hace |
|---|---|
| `/rutas/` | Mapa con filtro por sucursal, día y búsqueda. Pestañas: Localidades (totales por localidad y día), Camiones (carga por vehículo y día, y localidades con clientes pero sin camión), Pendientes y BEES. Tocando un cliente se cambian sus días, su nota o su ubicación (botón "Ubicar en el mapa"). |
| `/rutas/plan` | Recorrido semanal por vehículo (reemplaza la hoja INFORME), localidad → sucursal (reemplaza LOCALIDAD-SUCURSAL), alta y baja de vehículos, tope de clientes por día y ubicación de los depósitos. |

## 5. API

| Método | Ruta | Uso |
|---|---|---|
| GET | `/rutas/api/datos` | Clientes, plan, resumen y carga por día (todo lo que usa el mapa) |
| GET | `/rutas/api/resumen` | Totales y tabla por localidad |
| PATCH | `/rutas/api/clientes/<id>` | `{"dias":"MAVI", "lat":..., "lng":..., "nota":"..."}`. Con `lat`/`lng` en `null` vuelve a la ubicación del ERP |
| GET | `/rutas/api/clientes/<id>/historial` | Cambios del cliente (quién y cuándo) |
| PUT | `/rutas/api/vehiculos/<id>/plan` | `{"LU":["DOLORES"],"MA":["MAIPU","GENERAL GUIDO"],...}` |
| POST/PATCH | `/rutas/api/vehiculos[/<id>]` | Alta o edición de vehículo |
| POST/PUT | `/rutas/api/localidades[/<id>]` | Alta o edición de localidad (sucursal, centro) |
| PUT | `/rutas/api/depositos/<id>` | Dirección y coordenadas del depósito |
| GET | `/rutas/export/bees.xlsx` / `.csv` | Archivo para BEES (`?solo_pendientes=1` = solo los cambios) |
| POST | `/rutas/api/bees/marcar-exportados` | Limpia la marca de "pendiente de subir" |
| POST | `/rutas/api/sync` | Sync con ChessERP (requiere el header `X-Sync-Token`) |

## 6. Modelo de datos

```
rt_deposito ──< rt_localidad
     │
     └──< rt_vehiculo ──< rt_plan_ruta (día, localidad, orden)

rt_cliente  (espejo ERP, lo escribe la sync)
     └── rt_cliente_entrega  (días, ubicación corregida, nota: lo escribe la app)
rt_cambio_log   historial de cambios
rt_sync_log     cada importación o sync
```

El cliente se asocia a su localidad por el nombre de la localidad en el ERP (`localidad_erp` = `rt_localidad.nombre`). Una localidad del ERP que no está cargada en la tabla de localidades aparece con sucursal **SIN ASIGNAR**. Se agrega desde `/rutas/plan`.

**Reglas que usa la app:**

- *Ubicación a revisar*: coordenada fuera de la provincia de Buenos Aires, o a más de 15 km de la mediana de su localidad (`LEJOS_KM` en `services.py`).
- *Export BEES*: `Vendor_Account_ID = 13692800000000 + nº de cliente`, `DDC_ID = 1369280004`, mínimo y fee en 0, domingo siempre NO. Los anulados en el ERP no se exportan.
- *Días*: se guardan como `LUJU`, `MAVI`, etc. La conversión desde y hacia ChessERP (`"3,6"`) y BEES está en `dias.py`.

## 7. Correrlo solo (desarrollo o deploy propio en Railway)

```bash
cp .env.example .env     # completar DATABASE_URL y CHESS_*
pip install -r requirements.txt
flask --app app rutas seed
flask --app app rutas import-excel planilla.xlsm
flask --app app run      # http://localhost:5000/rutas/
```

En Railway, el `Procfile` ya levanta gunicorn.

## Pendientes conocidos

- **Depósitos:** las ubicaciones de Dolores y Chascomús son aproximadas (centro de la localidad) y Casa Central no tiene coordenadas. Hay que cargarlas en `/rutas/plan`.
- **Recorridos:** el mapa los dibuja en línea recta, depósito → localidades → depósito. El paso siguiente es ruteo real (OSRM o Google Directions) para kilómetros y orden de visita.
- **Cambios de días:** se guardan en la app y salen por el export de BEES. Pasarlos al ERP sigue siendo manual (la API de clientes que usamos es de lectura).
