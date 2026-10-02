"""Import weekly routes by branch, vehicle and day without changing customer days."""
import csv
import hashlib
import io
import json
from collections import defaultdict, Counter
from datetime import datetime, timezone
from uuid import uuid4
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy import text
from .db import Session
from .models import Deposito, Localidad, Vehiculo, PlanRuta, CambioLog, ImportacionRutas
from .localidades import normalizar_nombre as norm, SUCURSAL_POR_LOCALIDAD, sucursal_entrega
from .importar_dias import MAX_BYTES, MAX_ROWS, VistaDesactualizada

DAY = dict(zip(('LUNES','MARTES','MIERCOLES','JUEVES','VIERNES','SABADO'), ('LU','MA','MI','JU','VI','SA')))
DAY.update({d:d for d in DAY.values()})
HEAD = ('SUCURSAL','VEHICULO','DIA','LOCALIDAD','ORDEN')


def leer_csv(content):
    if not content or len(content)>MAX_BYTES:
        raise ValueError('Seleccioná un CSV de hasta 5 MB.')
    try:
        data=content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            data=content.decode('cp1252')
        except UnicodeDecodeError as exc:
            raise ValueError('Guardá el CSV como UTF-8.') from exc
    if not data.strip():
        raise ValueError('El CSV está vacío.')
    if '\x00' in data:
        raise ValueError('El archivo no es un CSV de texto.')
    reader=csv.DictReader(io.StringIO(data, newline=''), delimiter=max((';',',','\t'),key=data.splitlines()[0].count),strict=True)
    aliases={'CAMION':'VEHICULO','SUCURSAL QUE ENTREGA':'SUCURSAL'}
    try:
        fields=[aliases.get(norm(h),norm(h)) for h in (reader.fieldnames or [])]
        if len(fields)!=len(set(fields)) or not all(h in fields for h in HEAD):
            raise ValueError('Se requieren columnas únicas: SUCURSAL, VEHICULO, DIA, LOCALIDAD, ORDEN.')
        reader.fieldnames=fields
        rows=[]
        for r in reader:
            if not any(r.values()):
                continue
            if len(rows)>=MAX_ROWS:
                raise ValueError('Máximo: 20.000 paradas por archivo.')
            row={k.lower():norm(r.get(k)) for k in HEAD}
            row.update(fila=reader.line_num,error='')
            try:
                if None in r or any(v is None for v in r.values()):
                    raise ValueError('Cantidad de columnas incorrecta')
                if not row['vehiculo'] or len(row['vehiculo'])>60:
                    raise ValueError('Ingresá un vehículo de hasta 60 caracteres')
                if row['dia'] not in DAY:
                    raise ValueError('Día inválido: LUNES a SABADO o LU a SA')
                row['dia']=DAY[row['dia']]
                if not row['orden'].isdecimal() or not 1<=int(row['orden'])<=32767:
                    raise ValueError('Orden debe ser un entero entre 1 y 32767')
                row['orden']=int(row['orden'])
                if not row['sucursal'] or not row['localidad']:
                    raise ValueError('Falta sucursal o localidad')
            except ValueError as exc:
                row['error']=str(exc)
            rows.append(row)
    except csv.Error as exc:
        raise ValueError('CSV mal formado: revisá comillas y separadores.') from exc
    if not rows:
        raise ValueError('El CSV no contiene recorridos.')
    return rows


def catalogo(s):
    deps=defaultdict(list);locs=defaultdict(list);vehicles=defaultdict(list)
    for d in s.query(Deposito): deps[norm(d.nombre)].append(d)
    for l in s.query(Localidad): locs[norm(l.nombre)].append(l)
    for v in s.query(Vehiculo): vehicles[(norm(v.deposito.nombre),norm(v.nombre))].append(v)
    return deps,locs,vehicles


def snapshot(v,dia):
    return None if v is None else {'id':v.id,'activo':v.activo,'paradas':[
        [p.id,p.localidad_id,p.orden] for p in sorted(v.paradas,key=lambda p:(p.orden,p.id)) if p.dia==dia]}


def validar_grupo(group, catalogs):
    deps,locs,vehicles=catalogs
    branch=group['sucursal'];vs=vehicles.get((branch,group['vehiculo']),[])
    if branch not in set(SUCURSAL_POR_LOCALIDAD.values()) and branch not in deps:
        raise ValueError('Sucursal desconocida')
    if len(deps.get(branch,[]))>1 or len(vs)>1:
        raise ValueError('Sucursal o vehículo ambiguo en la base')
    v=vs[0] if vs else None
    if v and not v.activo:
        raise ValueError('El vehículo está inactivo')
    for stop in group['paradas']:
        name=stop['localidad'];matches=locs.get(name,[])
        if len(matches)>1:
            raise ValueError(f'Localidad duplicada en la base: {name}')
        fallback=matches[0].deposito.nombre if matches and matches[0].deposito else None
        if sucursal_entrega(name,fallback)!=branch:
            raise ValueError(f'{name}: localidad desconocida o asignada a otra sucursal')
    return v


def signer():
    return URLSafeTimedSerializer(current_app.secret_key,salt='rutas-importar-recorridos-v1')


def preparar(content,archivo,usuario,modo='vacios',actor=None):
    if modo not in {'vacios','reemplazar'}:
        raise ValueError('Modo de importación inválido')
    rows=leer_csv(content);groups={};errors=[]
    for r in rows:
        if r['error']:
            errors.append({'fila':r['fila'],'error':r['error']})
            continue
        key=(r['sucursal'],r['vehiculo'],r['dia'])
        group=groups.setdefault(key,dict(sucursal=r['sucursal'],vehiculo=r['vehiculo'],dia=r['dia'],paradas=[],filas=[]))
        group['paradas'].append({'localidad':r['localidad'],'orden':r['orden']});group['filas'].append(r['fila'])
    catalogs=catalogo(Session());changes=[];summary=Counter()
    for group in groups.values():
        group['error']='';group['actual']=[]
        try:
            stops=group['paradas']
            if len({p['orden'] for p in stops})!=len(stops) or len({p['localidad'] for p in stops})!=len(stops):
                raise ValueError('Orden o localidad repetidos para el mismo vehículo y día')
            stops.sort(key=lambda p:p['orden'])
            v=validar_grupo(group,catalogs)
            old=sorted((p for p in v.paradas if p.dia==group['dia']),key=lambda p:(p.orden,p.id)) if v else []
            group['actual']=[{'localidad':norm(p.localidad.nombre),'orden':p.orden} for p in old]
            group['nuevo_vehiculo']=v is None
            status='sin_cambios' if group['actual']==stops else 'conservar' if old and modo=='vacios' else 'reemplazar' if old else 'crear'
            group['estado']=status
            if status in {'crear','reemplazar'}:
                changes.append({**group,'antes':snapshot(v,group['dia'])})
            summary[status]+=1
        except ValueError as exc:
            group.update(estado='error',error=str(exc));summary['error']+=1
    result=dict(summary,total=len(groups),filas=len(rows),errores_fila=len(errors),cambios=len(changes))
    payload={'id':str(uuid4()),'archivo':archivo[:255],'sha256':hashlib.sha256(content).hexdigest(),
             'usuario':usuario,'actor':actor or usuario,'changes':changes,'resumen':result}
    return {'ok':True,'rows':list(groups.values()),'errores':errors,'resumen':result,
            'token':signer().dumps(payload) if changes and not errors and not summary['error'] else None}


def confirmar(token,usuario):
    if not isinstance(token,str) or len(token)>2_000_000:
        raise ValueError('Vista previa inválida')
    try:
        data=signer().loads(token,max_age=1800)
    except BadSignature as exc:
        raise ValueError('La vista previa venció o no es válida. Volvé a analizar el CSV.') from exc
    if data['usuario']!=usuario:
        raise ValueError('La vista previa pertenece a otro usuario')
    s=Session()
    try:
        if s.bind.dialect.name=='postgresql':
            s.execute(text('SELECT pg_advisory_xact_lock(7319021)'))
        done=s.get(ImportacionRutas,data['id'])
        if done:
            return {'ok':True,'ya_aplicada':True,'resumen':json.loads(done.resumen)}
        s.expire_all()
        catalogs=catalogo(s)
        for group in data['changes']:
            v=validar_grupo(group,catalogs)
            if snapshot(v,group['dia'])!=group['antes']:
                raise VistaDesactualizada('Los recorridos cambiaron desde la vista previa. Volvé a analizar; no se guardó ningún cambio.')
        deps,locs,vehicles=catalogs
        now=datetime.now(timezone.utc).replace(tzinfo=None)
        for group in data['changes']:
            branch=group['sucursal'];key=(branch,group['vehiculo'])
            if not deps.get(branch):
                dep=Deposito(nombre=branch);s.add(dep);s.flush();deps[branch]=[dep]
            dep=deps[branch][0]
            if not vehicles.get(key):
                v=Vehiculo(nombre=group['vehiculo'],deposito_id=dep.id,color='#2563eb');s.add(v);s.flush();vehicles[key]=[v]
            v=vehicles[key][0]
            s.query(PlanRuta).filter_by(vehiculo_id=v.id,dia=group['dia']).delete(synchronize_session=False)
            for stop in group['paradas']:
                name=stop['localidad']
                if not locs.get(name):
                    loc=Localidad(nombre=name,deposito_id=dep.id);s.add(loc);s.flush();locs[name]=[loc]
                s.add(PlanRuta(vehiculo_id=v.id,dia=group['dia'],localidad_id=locs[name][0].id,orden=stop['orden']))
            s.add(CambioLog(entidad='vehiculo',campo=f"plan:{v.id}:{group['dia']}",
                            antes=json.dumps(group['actual']),despues=json.dumps(group['paradas']),usuario=data['actor'],fecha=now))
        s.add(ImportacionRutas(id=data['id'],archivo=data['archivo'],sha256=data['sha256'],usuario=data['actor'],fecha=now,resumen=json.dumps(data['resumen'])))
        s.commit();s.expire_all()
        return {'ok':True,'ya_aplicada':False,'resumen':data['resumen']}
    except Exception:
        s.rollback();raise
