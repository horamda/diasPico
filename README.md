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
GET /api/v1/integracion/logistica/rechazos/clientes-diario?fecha=YYYY-MM-DD&empresa_id=1&sucursal=TODAS
GET /api/v1/integracion/logistica/pedidos?fecha=YYYY-MM-DD&empresa_id=1&sucursal=TODAS
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


## Rutas de entrega

Módulo integrado en `/rutas/` (mapa) y `/rutas/plan` (consulta de recorridos), con código en `app/rutas/`.

- Reiniciar la aplicación tras desplegar. La tarjeta se registra en el portal; los administradores la ven y pueden asignar el módulo a otros usuarios desde la administración de permisos.
- Rutas es solo de consulta: filtros, mapa, fichas e historial. No expone endpoints para editar clientes, ubicaciones, vehículos, localidades o recorridos.
- Se crean las localidades y depósitos del maestro. Las localidades de varias sucursales quedan sin asignar. Los vehículos y recorridos existentes se muestran sin edición; no se importa automáticamente la semilla del proyecto original.
- Los días de visita comercial no son días de entrega: los clientes nuevos empiezan sin días. Actualizar conserva los días, notas, coordenadas corregidas y asignaciones logísticas existentes.
- El historial de cada cliente está en su ficha del mapa. Registra usuario, fecha, campo y valores anterior/nuevo.
- Las tablas `rt_*` se crean al primer acceso autorizado a la API, usando el motor de la aplicación. El arranque no conecta a la base para crearlas. La base debe permitir crear tablas.
- El módulo actual admite códigos numéricos de cliente hasta 2147483647. La actualización informa los códigos omitidos; no combina identificadores que colisionan al convertirlos a número.
- La carga por camión representa cobertura por localidad, no asignación individual. Los trazos son orientativos, no rutas por calles. El export a BEES y la sincronización de clientes con Chess no están habilitados: los clientes salen del maestro y los días, del CSV. Desde Chess solo se cargan ventas (ver abajo).

Validación: `python -m pytest tests/test_rutas_entrega.py -q`.

### Pedidos, volumen y comportamiento de compra

Rutas lee las ventas de `ventas_detalle`, la misma tabla que se carga en Importaciones de datos y
que usan Días Pico y Drop Size, con sus mismas reglas (`app/rutas/ventas_app.py`):

- Se excluyen remitos (REMIT) y comodatos (COMOD).
- Bultos y HL cuentan solo artículos de tipo mercadería (sin envases ni esqueletos).
- Un **pedido** es un comprobante (`detalle_documento`); una **entrega**, un día con comprobantes del cliente.
  RMCYO cuenta como pedido y volumen, sin importe.
- La ventana termina en la última fecha cargada en `ventas_detalle`. Los resultados quedan en memoria
  10 minutos.

En el mapa, **Color por: Volumen** pinta y agranda los puntos según bultos por semana (quintiles), y al
elegir un día cada localidad muestra la **carga estimada** (suma del promedio de bultos por entrega de
sus clientes). La ficha del cliente tiene el panel **Pedidos y volumen** (30, 60 o 90 días): pedidos,
entregas, frecuencia, bultos y HL, promedio por entrega comparado con su localidad, venta neta, rechazo
y motivos, días de la semana en que recibe frente a sus días asignados, bultos por semana, últimos
pedidos y artículos más comprados. Estados: **inactivo** con más de 45 días sin comprar; **en riesgo**
con más de 2,5 veces su frecuencia habitual (mínimo 21 días). ABC por venta neta (80 / 15 / 5).

Opcional: `flask --app "app:create_app()" rutas sync-ventas` carga comprobantes desde la API de ChessERP
en `rt_venta` (login de frescura; ruta `CHESS_VENTAS_PATH` y formato `CHESS_FECHA_FMT` sin validar
contra la API real). El mapa no la usa.

Pruebas: `python -m pytest tests/test_rutas_ventas_app.py tests/test_rutas_ventas.py -q`.

### Importar días desde CSV

Desde **Importaciones de datos → Días de entrega** (`/importaciones/rutas/dias`), actualizar los clientes desde el maestro, seleccionar el CSV y **Analizar archivo**. Esta pantalla exige permiso de Importaciones de datos, independiente del acceso de lectura a Rutas.
El formato usa exclusivamente `CLIENTE` y `LUNES` a `SABADO`: un `1` indica visita
ese día; vacío o `0`, sin visita. Se normalizan espacios y tildes del encabezado.
Las columnas Mon–Sun de BEES, coordenadas, sucursales y anulado del CSV no se usan
para modificar el maestro.

La opción predeterminada completa días vacíos. **Reemplazar también días existentes**
permite modificar o quitar días según el archivo. La vista previa muestra cada fila
y excluye duplicados, códigos desconocidos, días inválidos y clientes inactivos en Rutas.
Actualizar el maestro antes de importar para trabajar con el estado vigente.

**Confirmar** aplica únicamente los cambios revisados, en una transacción. Si algún
cliente fue modificado desde el análisis, exige una nueva vista previa sin guardar
parcialmente. La vista previa vence a los 30 minutos y está ligada al usuario.
Reintentar la misma confirmación no duplica cambios. Los días se guardan en
`rt_cliente_entrega`, la auditoría en `rt_cambio_log` y el archivo/hash/resumen de
cada importación en `rt_importacion_dias`. El CSV original no se almacena.

Validación: `python -m pytest tests/test_rutas_importar_dias.py tests/test_rutas_entrega.py -q`.

En Rutas, un cliente activo debe permanecer activo en el maestro, tener `anulado = NO` y `fuerza_venta_1_dias_visita` no vacío y distinto de `DOM` (ignorando espacios extremos y mayúsculas). Esta condición se actualiza al sincronizar desde el maestro y determina también qué clientes admite la importación de días. Los días de visita se usan como filtro de actividad, no como días de entrega.


En el mapa de Rutas, el día seleccionado se combina con sucursal, búsqueda,
actividad y días asignados. Los puntos, tarjetas, tabla por localidad, pendientes
y cobertura por camión se recalculan sobre la misma selección. Seleccionar un día
centra el mapa en los clientes con coordenadas; los que carecen de ubicación siguen
contando en tarjetas y pendientes.

La relación operativa localidad–sucursal está definida en `app/rutas/localidades.py`
según la tabla de logística. Se aplica también a datos ya cargados, tiene prioridad
sobre la sucursal comercial del maestro y se persiste al actualizarlo. Normaliza
tildes y espacios repetidos. Incluye Casa Central, Chascomús y Dolores; las localidades
no incluidas conservan la asignación existente. No cambia coordenadas ni días.

### Importar rutas armadas por vehículo

En **Importaciones de datos → Rutas armadas por camión**, abrir
`/importaciones/rutas/recorridos`, descargar la plantilla CSV y reemplazar los ejemplos.
Una fila representa una localidad en un recorrido:

```csv
SUCURSAL;VEHICULO;DIA;LOCALIDAD;ORDEN
CHASCOMUS;CAMION 1;LUNES;CASTELLI;1
CHASCOMUS;CAMION 1;LUNES;LEZAMA;2
DOLORES;CAMION 2;MARTES;MAIPU;1
```

Admite días completos de lunes a sábado o LU/MA/MI/JU/VI/SA, UTF-8 o Windows-1252,
y separadores punto y coma, coma o tabulación. También acepta CAMION como encabezado
de VEHICULO. Normaliza espacios y tildes para identificar localidades y vehículos.

**Analizar archivo** muestra los recorridos actuales y propuestos. Por defecto conserva
los ya existentes; la opción de reemplazo modifica solo los vehículos y días presentes
en el archivo. Cada grupo debe traer su recorrido completo, con localidades y órdenes
sin repetir. Una localidad debe pertenecer a la sucursal indicada. Cualquier error
bloquea la confirmación de todo el archivo. Los vehículos nuevos se crean al confirmar;
los inactivos se rechazan y no se reactivan automáticamente.

La confirmación es transaccional, detecta vistas previas desactualizadas y tolera
reintentos sin duplicar importaciones. Guarda recorridos en `rt_plan_ruta`, vehículos
en `rt_vehiculo`, auditoría en `rt_cambio_log` y el resumen/hash del lote en
`rt_importacion_rutas`. No modifica los días de entrega de los clientes ni coordenadas.
Rutas sigue siendo solo de consulta. Reiniciar la app tras desplegar este cambio;
la nueva tabla de importaciones se crea en el primer acceso autorizado a la API.

Pruebas: `python -m pytest tests/test_rutas_importar_recorridos.py -q`.
