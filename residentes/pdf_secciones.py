"""Secciones clínicas del PDF del expediente (alergias, medicamentos,
signos vitales, valoración geriátrica, plan de atención, exámenes y citas).

Cada función recibe el residente y un `Kit` con los estilos del documento y
devuelve la lista de elementos (flowables) de su sección, o una lista vacía
si no hay nada que mostrar. Así el PDF solo lleva lo que tiene datos.
"""
from dataclasses import dataclass

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

ROJO = colors.HexColor('#B42318')
AMBAR = colors.HexColor('#8A6100')


@dataclass
class Kit:
    seccion: object
    label: object
    body: object
    encabezado: object
    azul_medio: object
    azul_claro: object
    azul_xclaro: object


def _p(texto, estilo):
    return Paragraph(escape(str(texto if texto not in (None, '') else '—')).replace('\n', '<br/>'), estilo)


def _fecha(valor, con_hora=False):
    if not valor:
        return '—'
    if hasattr(valor, 'hour'):
        valor = timezone.localtime(valor)
        return valor.strftime('%d/%m/%Y %H:%M' if con_hora else '%d/%m/%Y')
    return valor.strftime('%d/%m/%Y')


def tabla(kit, encabezados, filas, anchos):
    datos = [[Paragraph(escape(h), kit.encabezado) for h in encabezados]]
    for fila in filas:
        datos.append([c if hasattr(c, 'wrap') else _p(c, kit.body) for c in fila])
    t = Table(datos, colWidths=[a * inch for a in anchos], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), kit.azul_medio),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, kit.azul_xclaro]),
        ('GRID', (0, 0), (-1, -1), 0.3, kit.azul_claro),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t


# ── Alergias y antecedentes ─────────────────────────────────────

def alergias(residente, kit):
    from antecedentes.models import EstadoAlergias

    activas = list(residente.alergias.filter(activo=True))
    antecedentes = list(residente.antecedentes.filter(activo=True))
    estado = EstadoAlergias.objects.filter(residente=residente).first()
    story = [Paragraph(' Alergias y antecedentes', kit.seccion)]
    if activas:
        story.append(tabla(kit, ['Alergia', 'Tipo', 'Reacción', 'Severidad', 'Informó'], [
            [Paragraph(f'<font color="#B42318"><b>{escape(a.sustancia)}</b></font>', kit.body),
             a.get_tipo_display(),
             a.get_reaccion_display() + (f' — {a.descripcion_reaccion}' if a.descripcion_reaccion else ''),
             a.get_severidad_display(), a.get_fuente_display()]
            for a in activas
        ], [1.6, 1.0, 2.4, 0.9, 1.1]))
    elif estado and estado.sin_alergias_conocidas:
        story.append(_p('Sin alergias conocidas (confirmado el '
                        f'{_fecha(estado.fecha_actualizacion)}).', kit.body))
    else:
        story.append(_p('Alergias sin registrar: no se ha confirmado si tiene o no alergias.', kit.body))
    if antecedentes:
        story.append(Spacer(1, 4))
        story.append(tabla(kit, ['Antecedente', 'Tipo', 'Cuándo', 'Observaciones'], [
            [a.descripcion, a.get_tipo_display(), a.cuando, a.observaciones] for a in antecedentes
        ], [2.4, 1.2, 1.2, 2.2]))
    return story


# ── Medicamentos ────────────────────────────────────────────────

def medicamentos(residente, kit):
    from medicamentos.models import Prescripcion

    ordenes = list(
        Prescripcion.objects.filter(residente=residente, estado=Prescripcion.ACTIVA)
        .select_related('medicamento').prefetch_related('horarios').order_by('medicamento__nombre_generico')
    )
    if not ordenes:
        return [Paragraph(' Medicamentos (órdenes médicas activas)', kit.seccion),
                _p('Sin órdenes médicas activas.', kit.body)]
    filas = []
    for p in ordenes:
        if p.es_prn():
            horario = 'Si es necesario'
            if p.frecuencia_minima_horas:
                horario += f', cada {p.frecuencia_minima_horas} h como mínimo'
            if p.dosis_maxima_dia:
                horario += f', máximo {p.dosis_maxima_dia} al día'
        else:
            horario = ', '.join(h.hora.strftime('%H:%M') for h in p.horarios.all())
        dosis = f'{p.dosis_cantidad.normalize():f} {p.get_dosis_unidad_display()} · {p.get_via_administracion_display()}'
        filas.append([str(p.medicamento), dosis, horario,
                      f'{_fecha(p.fecha_inicio)} — {_fecha(p.fecha_fin) if p.fecha_fin else "indefinido"}',
                      f'{p.formulada_por} ({_fecha(p.fecha_formula)})'])
    return [Paragraph(' Medicamentos (órdenes médicas activas)', kit.seccion),
            tabla(kit, ['Medicamento', 'Dosis y vía', 'Horario', 'Vigencia', 'Formuló'], filas,
                  [1.8, 1.3, 1.4, 1.3, 1.2])]


# ── Signos vitales ──────────────────────────────────────────────

def signos(residente, kit, cantidad=10):
    controles = list(residente.controles_signos.filter(anulado=False).order_by('-fecha_hora')[:cantidad])
    if not controles:
        return []
    filas = []
    for c in controles:
        spo2 = f'{c.spo2}%' if c.spo2 is not None else ''
        if spo2 and c.oxigeno_suplementario:
            spo2 += ' (O2)'
        filas.append([
            _fecha(c.fecha_hora, con_hora=True), c.presion or '',
            c.fc if c.fc is not None else '', c.fr if c.fr is not None else '',
            c.temperatura if c.temperatura is not None else '', spo2,
            c.glucometria if c.glucometria is not None else '',
            c.dolor if c.dolor is not None else '', c.peso if c.peso is not None else '',
        ])
    return [Paragraph(f' Signos vitales (últimas {len(controles)} tomas)', kit.seccion),
            tabla(kit, ['Fecha', 'PA', 'FC', 'FR', 'T °C', 'SpO2', 'Gluc.', 'Dolor', 'Peso'], filas,
                  [1.4, 0.85, 0.55, 0.55, 0.65, 0.9, 0.7, 0.6, 0.8])]


# ── Valoración geriátrica ───────────────────────────────────────

def valoracion(residente, kit):
    ultimas = {}
    for v in residente.valoraciones.filter(anulada=False).order_by('-fecha', '-fecha_registro'):
        ultimas.setdefault(v.escala, v)
    if not ultimas:
        return []
    filas = []
    for v in ultimas.values():
        filas.append([v.definicion.nombre, v.puntaje, v.interpretacion, _fecha(v.fecha),
                      v.registrado_por.get_full_name() or v.registrado_por.username])
    return [Paragraph(' Valoración geriátrica (última de cada escala)', kit.seccion),
            tabla(kit, ['Escala', 'Puntaje', 'Interpretación', 'Fecha', 'Aplicó'], filas,
                  [1.9, 0.7, 2.3, 0.9, 1.2])]


# ── Plan de atención ────────────────────────────────────────────

def plan(residente, kit):
    from plan_atencion.models import PlanAtencion

    vigente = residente.planes_atencion.filter(estado=PlanAtencion.VIGENTE).first()
    if not vigente:
        return []
    story = [Paragraph(f' Plan de atención (versión {vigente.version}, '
                       f'próxima revisión {_fecha(vigente.fecha_revision)})', kit.seccion)]
    if vigente.resumen:
        story.append(Paragraph('Situación actual:', kit.label))
        story.append(_p(vigente.resumen, kit.body))
    objetivos = list(vigente.objetivos.all().order_by('area', 'fecha_meta'))
    if objetivos:
        story.append(tabla(kit, ['Área', 'Objetivo', 'Intervenciones', 'Responsable', 'Estado'], [
            [o.get_area_display(), o.meta, o.intervenciones + (f' ({o.frecuencia})' if o.frecuencia else ''),
             o.get_responsable_display(), f'{o.get_estado_display()} — evaluar {_fecha(o.fecha_meta)}']
            for o in objetivos
        ], [1.1, 1.9, 2.1, 1.0, 0.9]))
    if vigente.acuerdos_familia:
        story.append(Paragraph('Acuerdos con el residente y la familia:', kit.label))
        story.append(_p(vigente.acuerdos_familia, kit.body))
    return story


# ── Exámenes ────────────────────────────────────────────────────

def examenes(residente, kit, cantidad=10):
    from examenes.models import Examen, ValorResultado

    lista = list(
        residente.examenes.exclude(estado=Examen.CANCELADO)
        .order_by('-fecha_toma', '-fecha_registro')[:cantidad]
    )
    if not lista:
        return []
    marcas = {ValorResultado.CRITICO_BAJO: '↓↓', ValorResultado.BAJO: '↓',
              ValorResultado.ALTO: '↑', ValorResultado.CRITICO_ALTO: '↑↑'}
    filas = []
    for e in lista:
        valores = []
        for v in e.valores_vigentes():
            marca = marcas.get(v.interpretacion(), '')
            texto = escape(f'{v.nombre}: {v.valor_formateado} {v.unidad}'.strip())
            if marca:
                color = '#B42318' if 'critico' in v.interpretacion() else '#8A6100'
                texto = f'<font color="{color}"><b>{texto} {marca}</b></font>'
            valores.append(texto)
        revision = e.ultima_revision()
        detalle = '; '.join(valores) or escape(e.conclusion or '')
        if revision:
            detalle += f'<br/><i>Conducta: {escape(revision.conducta)}</i>'
        filas.append([e.nombre, _fecha(e.fecha_toma or e.fecha_orden), e.get_estado_display(),
                      Paragraph(detalle or '—', kit.body)])
    return [Paragraph(f' Exámenes (últimos {len(lista)})', kit.seccion),
            tabla(kit, ['Examen', 'Toma', 'Estado', 'Resultados y conducta'], filas, [1.6, 0.8, 1.2, 3.4])]


# ── Citas ───────────────────────────────────────────────────────

def citas(residente, kit):
    from citas.models import Cita

    ahora = timezone.now()
    proximas = list(residente.citas.filter(estado=Cita.PROGRAMADA, fecha_hora__gte=ahora).order_by('fecha_hora')[:10])
    recientes = list(residente.citas.filter(fecha_hora__lt=ahora).exclude(estado=Cita.REPROGRAMADA)
                     .order_by('-fecha_hora')[:5])
    if not proximas and not recientes:
        return []
    story = [Paragraph(' Citas médicas', kit.seccion)]
    if proximas:
        story.append(Paragraph('Próximas:', kit.label))
        story.append(tabla(kit, ['Fecha', 'Cita', 'Lugar', 'Indicaciones'], [
            [_fecha(c.fecha_hora, con_hora=True), c.titulo, c.lugar,
             ('Ayuno. ' if c.requiere_ayuno else '') + (c.preparacion or '')]
            for c in proximas
        ], [1.2, 1.8, 2.2, 1.8]))
    if recientes:
        story.append(Paragraph('Recientes:', kit.label))
        story.append(tabla(kit, ['Fecha', 'Cita', 'Resultado', 'Qué pasó'], [
            [_fecha(c.fecha_hora, con_hora=True), c.titulo,
             'Sin registrar qué pasó' if c.abierta else c.get_estado_display(), c.resumen]
            for c in recientes
        ], [1.2, 1.8, 1.1, 2.9]))
    return story


# ── Cuidados y heridas ──────────────────────────────────────────

def cuidados(residente, kit):
    from cuidados.models import Herida, PlanCuidados, TIPOS_CUIDADO

    heridas = list(residente.heridas.filter(estado=Herida.ACTIVA))
    try:
        plan = residente.plan_cuidados
    except PlanCuidados.DoesNotExist:
        plan = None
    if not heridas and plan is None:
        return []
    story = [Paragraph(' Cuidados y heridas', kit.seccion)]
    if plan is not None:
        nombres = dict(TIPOS_CUIDADO)
        partes = []
        for t in plan.tipos():
            texto = nombres[t]
            if t == 'posicion':
                texto += f' ({plan.get_intervalo_posicion_horas_display().lower()})'
            if t == 'banio':
                texto += f' ({plan.get_banio_display().lower()})'
            partes.append(texto)
        story.append(Paragraph('Plan de cuidados:', kit.label))
        story.append(_p(', '.join(partes) or 'Sin cuidados marcados.', kit.body))
        if plan.indicaciones:
            story.append(_p(plan.indicaciones, kit.body))
    if heridas:
        filas = []
        for h in heridas:
            s = h.ultimo_seguimiento()
            ultimo = '—'
            if s:
                ultimo = _fecha(s.fecha_hora, con_hora=True)
                if s.area_cm2 is not None:
                    ultimo += f' · {s.largo_cm} × {s.ancho_cm} cm'
                if s.signos_infeccion:
                    ultimo += ' · signos de infección'
                if s.curacion:
                    ultimo += f' · {s.curacion}'
            filas.append([h.nombre, h.estadio_actual or '—', f'{_fecha(h.fecha_deteccion)} ({h.get_origen_display().lower()})', ultimo])
        story.append(tabla(kit, ['Herida', 'Estadio', 'Detectada', 'Último seguimiento y curación'], filas,
                           [1.9, 0.9, 1.6, 2.6]))
    return story


# ── Nutrición ───────────────────────────────────────────────────

def nutricion(residente, kit):
    from nutricion import services as ns
    from nutricion.models import ConfiguracionNutricion

    dieta = ns.dieta_vigente(residente)
    config = ConfiguracionNutricion.para_hogar(residente.hogar)
    cuadricula = ns.cuadricula(residente, config, dias=7)
    hay_ingesta = any(c for f in cuadricula for c in f['celdas']) or any(f['liquidos'] for f in cuadricula)
    if not dieta and not hay_ingesta:
        return []
    story = [Paragraph(' Nutrición e hidratación', kit.seccion)]
    if dieta:
        partes = [dieta.resumen, dieta.get_ayuda_display().lower(),
                  f'meta de líquidos {ns.meta_liquidos(residente, dieta, config)} mL']
        if dieta.restriccion_liquidos_ml:
            partes.append(f'máximo {dieta.restriccion_liquidos_ml} mL')
        story.append(Paragraph('Dieta:', kit.label))
        story.append(_p(', '.join(partes) + (f'. Evitar: {dieta.alimentos_evitar}' if dieta.alimentos_evitar else ''), kit.body))
    if hay_ingesta:
        nombres = [n for _, n, _ in config.comidas()]
        filas = []
        for f in cuadricula:
            filas.append([f['fecha'].strftime('%d/%m')]
                         + [(c.get_consumo_display() if c else '—') for c in f['celdas']]
                         + [f"{f['promedio']} %" if f['promedio'] is not None else '—',
                            f"{f['liquidos']} mL" if f['liquidos'] else '—'])
        ancho = 4.6 / max(1, len(nombres))
        story.append(tabla(kit, ['Día', *nombres, 'Prom.', 'Líquidos'], filas,
                           [0.6, *([ancho] * len(nombres)), 0.7, 0.9]))
    return story


SECCIONES = {
    'alergias': ('Alergias y antecedentes', alergias),
    'medicamentos': ('Medicamentos (órdenes activas)', medicamentos),
    'signos': ('Signos vitales (últimas 10 tomas)', signos),
    'valoracion': ('Valoración geriátrica', valoracion),
    'plan': ('Plan de atención vigente', plan),
    'examenes_clinicos': ('Exámenes (últimos 10)', examenes),
    'citas': ('Citas médicas', citas),
    'cuidados': ('Cuidados y heridas', cuidados),
    'nutricion': ('Nutrición e hidratación', nutricion),
}
