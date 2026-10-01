"""Reglas de negocio del módulo de exámenes.

Las vistas solo validan formularios y llaman aquí; las transiciones de
estado y la escritura de filas inmutables viven en un solo lugar, con su
transacción, para que las pruebas las ejerzan directamente.
"""
import hashlib

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ArchivoResultado, Examen, RevisionMedica, ValorResultado


def _hash_archivo(archivo):
    h = hashlib.sha256()
    archivo.seek(0)
    for bloque in archivo.chunks():
        h.update(bloque)
    archivo.seek(0)
    return h.hexdigest()


def _guardar_archivos(examen, archivos, usuario, motivo=''):
    creados = []
    for archivo in archivos:
        content_type = getattr(archivo, 'tipo_detectado', None) or archivo.content_type
        fila = ArchivoResultado(
            examen=examen,
            nombre_original=archivo.name[:255],
            content_type=content_type,
            tamano_bytes=archivo.size,
            sha256=_hash_archivo(archivo),
            motivo=motivo,
            subido_por=usuario,
        )
        fila.archivo.save(archivo.name, archivo, save=False)
        fila.save()
        creados.append(fila)
    return creados


def _guardar_valores(examen, valores, usuario):
    creados = []
    for v in valores:
        creados.append(ValorResultado.objects.create(
            examen=examen,
            analito=v.get('analito'),
            nombre=v['nombre'],
            valor=v['valor'],
            unidad=v.get('unidad') or '',
            ref_min=v.get('ref_min'),
            ref_max=v.get('ref_max'),
            registrado_por=usuario,
        ))
    return creados


@transaction.atomic
def cargar_resultado(examen, usuario, fecha_toma, conclusion='', archivos=(), valores=()):
    """Primer resultado de un examen pendiente → queda para revisión médica."""
    examen = Examen.objects.select_for_update().get(pk=examen.pk)
    if examen.estado != Examen.PENDIENTE:
        raise ValidationError('Este examen ya tiene resultado o fue cancelado.')
    if not archivos and not valores and not conclusion.strip():
        raise ValidationError(
            'Adjunte al menos un archivo, registre un valor o escriba la conclusión del informe.'
        )
    _guardar_archivos(examen, archivos, usuario)
    _guardar_valores(examen, valores, usuario)
    examen.fecha_toma = fecha_toma
    examen.conclusion = conclusion.strip()
    examen.estado = Examen.RESULTADO
    examen.resultado_cargado_por = usuario
    examen.fecha_resultado = timezone.now()
    examen.save()
    return examen


@transaction.atomic
def agregar_adenda(examen, usuario, motivo, archivos=(), valores=()):
    """Información nueva sobre un resultado ya cargado. Si ya estaba
    revisado, vuelve a pendiente de revisión."""
    examen = Examen.objects.select_for_update().get(pk=examen.pk)
    if examen.estado not in (Examen.RESULTADO, Examen.REVISADO):
        raise ValidationError('Solo se agrega información a exámenes que ya tienen resultado.')
    if not motivo.strip():
        raise ValidationError('La información adicional necesita un motivo.')
    if not archivos and not valores:
        raise ValidationError('Adjunte al menos un archivo o registre al menos un valor.')
    _guardar_archivos(examen, archivos, usuario, motivo=motivo.strip())
    _guardar_valores(examen, valores, usuario)
    if examen.estado == Examen.REVISADO:
        examen.estado = Examen.RESULTADO
        examen.save(update_fields=['estado'])
    return examen


@transaction.atomic
def corregir_valor(valor, usuario, nuevo_valor, unidad, ref_min, ref_max, motivo):
    """Crea un valor nuevo que reemplaza al anterior; el original no se toca."""
    valor = ValorResultado.objects.select_for_update().get(pk=valor.pk)
    if hasattr(valor, 'corregido_por'):
        raise ValidationError('Este valor ya fue corregido; corrija la versión vigente.')
    if not motivo.strip():
        raise ValidationError('La corrección necesita un motivo.')
    examen = Examen.objects.select_for_update().get(pk=valor.examen_id)
    if examen.estado not in (Examen.RESULTADO, Examen.REVISADO):
        raise ValidationError('El examen no admite correcciones en su estado actual.')
    nuevo = ValorResultado.objects.create(
        examen=examen,
        analito=valor.analito,
        nombre=valor.nombre,
        valor=nuevo_valor,
        unidad=unidad or valor.unidad,
        ref_min=ref_min,
        ref_max=ref_max,
        critico_min=valor.critico_min,
        critico_max=valor.critico_max,
        reemplaza=valor,
        motivo_correccion=motivo.strip(),
        registrado_por=usuario,
    )
    if examen.estado == Examen.REVISADO:
        examen.estado = Examen.RESULTADO
        examen.save(update_fields=['estado'])
    return nuevo


@transaction.atomic
def revisar(examen, medico, conducta, interpretacion=''):
    examen = Examen.objects.select_for_update().get(pk=examen.pk)
    if examen.estado != Examen.RESULTADO:
        raise ValidationError('Solo se revisan exámenes con resultado pendiente de revisión.')
    if not conducta.strip():
        raise ValidationError('La revisión necesita una conducta.')
    revision = RevisionMedica.objects.create(
        examen=examen, medico=medico,
        interpretacion=interpretacion.strip(), conducta=conducta.strip(),
    )
    examen.estado = Examen.REVISADO
    examen.save(update_fields=['estado'])
    return revision


@transaction.atomic
def cancelar(examen, usuario, motivo):
    examen = Examen.objects.select_for_update().get(pk=examen.pk)
    if examen.estado != Examen.PENDIENTE:
        raise ValidationError('Solo se cancelan órdenes que aún no tienen resultado.')
    if not motivo.strip():
        raise ValidationError('La cancelación necesita un motivo.')
    examen.estado = Examen.CANCELADO
    examen.cancelado_por = usuario
    examen.fecha_cancelacion = timezone.now()
    examen.motivo_cancelacion = motivo.strip()
    examen.save()
    return examen


def resumen_hogar(hogar):
    """Conteos para la bandeja del hogar y, más adelante, el motor de alertas."""
    base = Examen.objects.filter(residente__hogar=hogar, residente__activo=True)
    por_revisar = list(base.filter(estado=Examen.RESULTADO).prefetch_related('valores'))
    return {
        'pendientes': base.filter(estado=Examen.PENDIENTE).count(),
        'por_revisar': len(por_revisar),
        'criticos_sin_revisar': sum(1 for e in por_revisar if e.tiene_criticos()),
    }
