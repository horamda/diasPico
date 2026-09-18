# Control de frescura: revision, cierre y tiempos

1. Seleccionar sucursal, fecha del control y operario, y cargar la planilla.
2. Pulsar **Iniciar / recuperar control**. El servidor registra el inicio y conserva la planilla esperada para esa sesion.
3. Los lotes y pallets comienzan pendientes. En **Revisar pallets / fechas**, la cantidad de pallets se obtiene del stock y los bultos por pallet del maestro. Sin esa equivalencia se muestra el lote completo, sin inventar una cantidad de pallets.
4. Confirmar **OK** tras revisar fisicamente, o **No OK** y el vencimiento encontrado. La confirmacion conjunta de pendientes requiere una confirmacion explicita. Aplicar el avance para incorporarlo al borrador.
5. **Pausar y guardar borrador** detiene el tiempo activo. **Salir del control pausado** permite seleccionar otro contexto. Para recuperar, seleccionar la misma sucursal, fecha y operario y pulsar Iniciar / recuperar; la recuperacion no reinicia el reloj.
6. **Guardar control de frescura** finaliza cuando todos los lotes/pallets estan revisados. La escritura del control y el cierre del tiempo ocurren en la misma transaccion.

El resumen final lista los No OK de fecha por pallet/grupo, con cantidad afectada y vencimientos esperado/real. Las diferencias de cantidad se informan una sola vez por lote, separadas de las diferencias de fecha. Los pallets OK no se incluyen como hallazgos.

El historial permite filtrar fechas, sucursal y nombre exacto del operario, ver tiempos y consultar los No OK de un control particular. Los controles antiguos sin tiempo guardado se muestran como **Sin medicion** y no se cuentan como controles medidos.

## Tiempo y borrador

- **Tiempo activo**: intervalos entre inicio/reanudacion y pausa/finalizacion.
- **Tiempo transcurrido**: desde inicio hasta finalizacion, incluyendo pausas; soporta cruces de medianoche.
- Cerrar el navegador, perder conexion o cambiar de solapa **no pausa** el control. Es necesario pulsar Pausar al interrumpir el trabajo.
- Se guarda el borrador al editar y al pausar. Dentro del editor de pallets, primero se debe aplicar el avance. La pantalla informa fallos de guardado; no se considera que exista respaldo en el servidor si la solicitud falla.
- Sucursal, fecha, operario y stock esperado quedan fijos durante la sesion.

## Datos y activacion

`control_frescura_sesiones` conserva estado, reloj y borrador. `control_frescura_conteos` guarda inicio, fin, segundos activos y transcurridos. `control_frescura_conteo_items.distribucion_fechas` conserva la revision de cada pallet/grupo.

Las migraciones `20260910_frescura_distribucion_fechas.sql` y `20260910_frescura_tiempos.sql` son aditivas. Tambien se aplican mediante la inicializacion habitual del modulo al cargar el backend actualizado. Debe reiniciarse o desplegarse el proceso del backend junto con la plantilla y el nuevo archivo JavaScript.

Endpoints:

- `POST /api/control-stock/frescura-sesiones`: iniciar o recuperar.
- `PUT /api/control-stock/frescura-sesiones/<id>`: borrador, pausar, reanudar.
- `POST /api/control-stock/frescura-conteos`: finalizar, requiere `sesion_id`.
- `GET /api/control-stock/frescura-tiempos`: historial y totales por sucursal/operario.
- `GET /api/control-stock/frescura-diferencias?conteo_id=...`: diferencias de un control, con filtros de sucursal/periodo.
