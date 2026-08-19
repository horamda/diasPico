# Dashboard Dias Pico

Panel Flask para cargar archivos de reparto, articulos, clientes, feriados y motivos de rechazo, y calcular indicadores operativos por mes y por dia.

## Ejecutar local

Desde la carpeta del proyecto:

```powershell
.\venv\Scripts\python.exe run.py
```

Abrir:

```text
http://localhost:5001/
```

Paginas disponibles:

```text
http://localhost:5001/
http://localhost:5001/login
http://localhost:5001/setup-inicial
http://localhost:5001/portal
http://localhost:5001/portal/admin
http://localhost:5001/dashboard
http://localhost:5001/dias-pico
http://localhost:5001/reporte-picos
http://localhost:5001/segmentacion-clientes
```

Portal de accesos:

- Los usuarios y modulos se guardan en PostgreSQL (sin hardcodeo en codigo).
- Primera vez: abrir `/setup-inicial` para crear el admin.
- Luego: ingresar por `/login`.
- CRUD de usuarios, modulos y asignacion de accesos por usuario en `/portal/admin`.

Health check:

```text
http://localhost:5001/api/health
```

## Configuracion

Crear un archivo `.env` con las conexiones:

```text
DATABASE_URL=postgresql://...
# RAILWAY_URL tambien funciona como alias local
MYSQL_HOST=...
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DB=...
SHEETS_TIMEOUT=10
SECRET_KEY=...
```

`DATABASE_URL` es la variable recomendada para PostgreSQL en Railway. `RAILWAY_URL` se mantiene como alias por compatibilidad. Las variables `MYSQL_*` se usan solo si el modulo externo de ausentismo esta disponible.

## Deploy en Railway

El repo ya incluye lo necesario para Railway:

- `railway.toml`: usa Nixpacks, healthcheck en `/api/health` y start command con Gunicorn.
- `Procfile`: comando web equivalente para entornos que lo usen.
- `.python-version`: fija Python 3.12.
- `requirements.txt`: incluye `gunicorn` y dependencias de Flask/PostgreSQL.

Variables minimas en Railway:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=<generar-con-python -c "import secrets; print(secrets.token_hex(32))">
FLASK_ENV=production
```

Variables opcionales segun modulos activos:

```text
EXTERNAL_API_BASE_URL=...
EXTERNAL_API_KEY=...
SHEETS_TIMEOUT=30
DOTACION_ENTREGA_URL=...
DOTACION_RECARGAS_URL=...
PG_POOL_MAX=10
```

Para Frescura, configurar tambien estas variables si se usa el modulo de oportunidades:

```text
FRESCURA_API_BASE_URL=https://delpalacio.chesserp.com/AR459/web/api/chess/v1
FRESCURA_API_USER=...
FRESCURA_API_PASSWORD=...
FRESCURA_API_DEPOSITOS=1,4
FRESCURA_API_DEPOSIT_MAP=1:1,4:2
FRESCURA_API_TIMEOUT=60
```

La sincronizacion manual se ejecuta desde `GET /api/frescura/sync`. Para sincronizacion automatica, crear un job/cron en el entorno de deploy que ejecute:

```bash
python scripts/sync_frescura.py
```

No configurar `PORT` manualmente: Railway lo inyecta y el start command hace bind a `0.0.0.0:$PORT`.

## Carga de datos

El panel permite cargar:

- Articulos CSV: reemplaza la tabla `articulos`.
- Resumen repartos Excel: reemplaza el mes actual o meses historicos si se usa `Force`.
- Detalle repartos Excel: reemplaza el mes actual o meses historicos si se usa `Force`.
- Clientes CSV.
- Motivos de rechazo Excel.

Los indicadores de detalle usan solo articulos con `tipo_producto = mercaderia`. Los articulos del detalle que no existan en la tabla `articulos` se informan como "sin clasificar" y quedan fuera del calculo.

## Endpoints utiles

Contrato completo y rutas recomendadas por modulo: [`docs/API_CONTRATO.md`](docs/API_CONTRATO.md).

```text
GET /api/articulos/count
GET /api/articulos/sin-clasificar?mes=YYYY-MM&sucursal=TODAS
GET /api/picos/calendario?mes=YYYY-MM&sucursal=TODAS
GET /api/picos/kpis?mes=YYYY-MM&sucursal=TODAS
GET /api/picos/historico?sucursal=TODAS&meses=12
GET /api/picos/venta-dia?sucursal=TODAS&periodo_tipo=anio&anio=2026
GET /api/picos/venta-dia?sucursal=TODAS&periodo_tipo=mes&mes=2026-06
GET /api/picos/venta-dia/export?sucursal=TODAS&periodo_tipo=anio&anio=2026&formato=xlsx
GET /api/picos/venta-dia/export?sucursal=TODAS&periodo_tipo=anio&anio=2026&formato=pdf
GET /api/rechazos
GET /api/rechazos/diario/resumen?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&sucursal=TODAS
GET /api/rechazos/diario/detalle?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&sucursal=TODAS
GET /api/rechazos/diario/integracion?desde=YYYY-MM-DD&hasta=YYYY-MM-DD&sucursal=TODAS
GET /api/admin-proyecto/dashboard
GET /api/admin-proyecto/tablas
GET /api/admin-proyecto/indices
GET /api/admin-proyecto/candidatas-limpieza
GET /api/segmentacion/periodo
PUT /api/segmentacion/periodo
GET /api/segmentacion/score-pesos
PUT /api/segmentacion/score-pesos
GET /api/segmentacion/cache
POST /api/segmentacion/cache/refresh
POST /api/segmentacion/recalcular
```

`venta-dia` acepta `periodo_tipo=todo|mes|anio|semana|rango` y devuelve comparativos ISO semana a semana para el año seleccionado.
