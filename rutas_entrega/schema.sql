-- Esquema del módulo Rutas de Entrega (PostgreSQL). Alternativa a `flask rutas init-db`.

CREATE TABLE rt_cambio_log (
	id SERIAL NOT NULL, 
	id_cliente INTEGER, 
	entidad VARCHAR(30) NOT NULL, 
	campo VARCHAR(40) NOT NULL, 
	antes TEXT, 
	despues TEXT, 
	usuario VARCHAR(120), 
	fecha TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_rt_cambio_log_id_cliente ON rt_cambio_log (id_cliente);

CREATE TABLE rt_cliente (
	id_cliente INTEGER NOT NULL, 
	id_sucursal_erp INTEGER, 
	razon_social VARCHAR(200), 
	fantasia VARCHAR(200), 
	domicilio VARCHAR(200), 
	localidad_erp VARCHAR(80), 
	lat FLOAT, 
	lng FLOAT, 
	dias_erp VARCHAR(12) NOT NULL, 
	vendedor VARCHAR(120), 
	ruta_venta VARCHAR(20), 
	ruta_distribucion VARCHAR(80), 
	horario VARCHAR(120), 
	canal VARCHAR(80), 
	anulado BOOLEAN NOT NULL, 
	sincronizado TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id_cliente)
);

CREATE TABLE rt_deposito (
	id SERIAL NOT NULL, 
	nombre VARCHAR(60) NOT NULL, 
	direccion VARCHAR(200), 
	lat FLOAT, 
	lng FLOAT, 
	PRIMARY KEY (id), 
	UNIQUE (nombre)
);

CREATE TABLE rt_sync_log (
	id SERIAL NOT NULL, 
	origen VARCHAR(30) NOT NULL, 
	inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fin TIMESTAMP WITHOUT TIME ZONE, 
	leidos INTEGER NOT NULL, 
	nuevos INTEGER NOT NULL, 
	actualizados INTEGER NOT NULL, 
	error TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE rt_cliente_entrega (
	id_cliente INTEGER NOT NULL, 
	dias VARCHAR(12) NOT NULL, 
	lat FLOAT, 
	lng FLOAT, 
	nota TEXT, 
	en_planilla BOOLEAN NOT NULL, 
	pendiente_bees BOOLEAN NOT NULL, 
	actualizado TIMESTAMP WITHOUT TIME ZONE, 
	actualizado_por VARCHAR(120), 
	PRIMARY KEY (id_cliente), 
	FOREIGN KEY(id_cliente) REFERENCES rt_cliente (id_cliente)
);

CREATE TABLE rt_localidad (
	id SERIAL NOT NULL, 
	nombre VARCHAR(80) NOT NULL, 
	deposito_id INTEGER, 
	lat FLOAT, 
	lng FLOAT, 
	PRIMARY KEY (id), 
	UNIQUE (nombre), 
	FOREIGN KEY(deposito_id) REFERENCES rt_deposito (id)
);

CREATE TABLE rt_vehiculo (
	id SERIAL NOT NULL, 
	deposito_id INTEGER NOT NULL, 
	nombre VARCHAR(60) NOT NULL, 
	patente VARCHAR(20), 
	capacidad_clientes INTEGER, 
	color VARCHAR(9) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(deposito_id) REFERENCES rt_deposito (id)
);

CREATE TABLE rt_plan_ruta (
	id SERIAL NOT NULL, 
	vehiculo_id INTEGER NOT NULL, 
	dia VARCHAR(2) NOT NULL, 
	localidad_id INTEGER NOT NULL, 
	orden SMALLINT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (vehiculo_id, dia, localidad_id), 
	FOREIGN KEY(vehiculo_id) REFERENCES rt_vehiculo (id) ON DELETE CASCADE, 
	FOREIGN KEY(localidad_id) REFERENCES rt_localidad (id)
);
