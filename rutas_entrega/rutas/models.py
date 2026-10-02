"""Tablas del módulo (prefijo rt_).

Dos capas separadas a propósito:
  * rt_cliente           -> espejo del ERP. Lo pisa la sincronización, nunca se edita a mano.
  * rt_cliente_entrega   -> lo que decide logística (días, ubicación corregida). La sync no lo toca.
Así se puede re-sincronizar el ERP todos los días sin perder el armado de días.
"""
from datetime import datetime
from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, SmallInteger, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Deposito(Base):
    """Sucursal desde donde salen los camiones."""
    __tablename__ = "rt_deposito"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    direccion: Mapped[str | None] = mapped_column(String(200))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "direccion": self.direccion, "lat": self.lat, "lng": self.lng}


class Localidad(Base):
    """Reemplaza la hoja LOCALIDAD-SUCURSAL."""
    __tablename__ = "rt_localidad"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    deposito_id: Mapped[int | None] = mapped_column(ForeignKey("rt_deposito.id"))
    lat: Mapped[float | None] = mapped_column(Float)   # centro, se usa para dibujar el recorrido
    lng: Mapped[float | None] = mapped_column(Float)
    deposito: Mapped[Deposito | None] = relationship()

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "deposito_id": self.deposito_id,
                "deposito": self.deposito.nombre if self.deposito else None, "lat": self.lat, "lng": self.lng}


class Vehiculo(Base):
    __tablename__ = "rt_vehiculo"
    id: Mapped[int] = mapped_column(primary_key=True)
    deposito_id: Mapped[int] = mapped_column(ForeignKey("rt_deposito.id"))
    nombre: Mapped[str] = mapped_column(String(60))
    patente: Mapped[str | None] = mapped_column(String(20))
    capacidad_clientes: Mapped[int | None] = mapped_column(Integer)  # tope orientativo de entregas/día
    color: Mapped[str] = mapped_column(String(9), default="#c4561e")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    deposito: Mapped[Deposito] = relationship()
    paradas: Mapped[list["PlanRuta"]] = relationship(back_populates="vehiculo", cascade="all, delete-orphan",
                                                     order_by="PlanRuta.dia, PlanRuta.orden")

    def to_dict(self):
        plan = {}
        for p in self.paradas:
            plan.setdefault(p.dia, []).append(p.localidad.nombre)
        return {"id": self.id, "nombre": self.nombre, "patente": self.patente, "color": self.color,
                "capacidad_clientes": self.capacidad_clientes, "activo": self.activo,
                "deposito_id": self.deposito_id, "deposito": self.deposito.nombre, "plan": plan}


class PlanRuta(Base):
    """Reemplaza la hoja INFORME: qué localidades visita cada vehículo cada día, en orden."""
    __tablename__ = "rt_plan_ruta"
    __table_args__ = (UniqueConstraint("vehiculo_id", "dia", "localidad_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("rt_vehiculo.id", ondelete="CASCADE"))
    dia: Mapped[str] = mapped_column(String(2))          # LU..SA
    localidad_id: Mapped[int] = mapped_column(ForeignKey("rt_localidad.id"))
    orden: Mapped[int] = mapped_column(SmallInteger, default=1)
    vehiculo: Mapped[Vehiculo] = relationship(back_populates="paradas")
    localidad: Mapped[Localidad] = relationship()


class Cliente(Base):
    """Espejo de ChessERP. Solo lo escribe la sincronización / importación."""
    __tablename__ = "rt_cliente"
    id_cliente: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    id_sucursal_erp: Mapped[int | None] = mapped_column(Integer)
    razon_social: Mapped[str | None] = mapped_column(String(200))
    fantasia: Mapped[str | None] = mapped_column(String(200))
    domicilio: Mapped[str | None] = mapped_column(String(200))
    localidad_erp: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    dias_erp: Mapped[str] = mapped_column(String(12), default="")
    vendedor: Mapped[str | None] = mapped_column(String(120))
    ruta_venta: Mapped[str | None] = mapped_column(String(20))
    ruta_distribucion: Mapped[str | None] = mapped_column(String(80))
    horario: Mapped[str | None] = mapped_column(String(120))
    canal: Mapped[str | None] = mapped_column(String(80))
    anulado: Mapped[bool] = mapped_column(Boolean, default=False)
    sincronizado: Mapped[datetime | None] = mapped_column(DateTime)
    entrega: Mapped["ClienteEntrega | None"] = relationship(uselist=False, lazy="joined")


class ClienteEntrega(Base):
    """Armado de logística por cliente. Lo edita la app."""
    __tablename__ = "rt_cliente_entrega"
    id_cliente: Mapped[int] = mapped_column(ForeignKey("rt_cliente.id_cliente"), primary_key=True)
    dias: Mapped[str] = mapped_column(String(12), default="")
    lat: Mapped[float | None] = mapped_column(Float)     # ubicación corregida (pisa la del ERP)
    lng: Mapped[float | None] = mapped_column(Float)
    nota: Mapped[str | None] = mapped_column(Text)
    en_planilla: Mapped[bool] = mapped_column(Boolean, default=True)
    pendiente_bees: Mapped[bool] = mapped_column(Boolean, default=False)  # cambiado desde el último export
    actualizado: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado_por: Mapped[str | None] = mapped_column(String(120))


class CambioLog(Base):
    __tablename__ = "rt_cambio_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    id_cliente: Mapped[int | None] = mapped_column(Integer, index=True)
    entidad: Mapped[str] = mapped_column(String(30), default="cliente")
    campo: Mapped[str] = mapped_column(String(40))
    antes: Mapped[str | None] = mapped_column(Text)
    despues: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[str | None] = mapped_column(String(120))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SyncLog(Base):
    __tablename__ = "rt_sync_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    origen: Mapped[str] = mapped_column(String(30))
    inicio: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fin: Mapped[datetime | None] = mapped_column(DateTime)
    leidos: Mapped[int] = mapped_column(Integer, default=0)
    nuevos: Mapped[int] = mapped_column(Integer, default=0)
    actualizados: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
