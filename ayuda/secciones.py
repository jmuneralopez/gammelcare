"""Ayuda en contexto: qué es cada sección y qué puede hacer cada rol en ella.

Los roles de cada acción salen de las mismas listas que usan los permisos
de cada módulo, para que la ayuda nunca diga algo distinto de lo que el
sistema realmente permite. Si cambia un permiso, la ayuda cambia sola.

Cada acción es (texto, roles). Una acción con `roles=None` la puede hacer
cualquiera que tenga acceso a la sección.
"""
from dataclasses import dataclass, field

from usuarios.models import Rol


@dataclass
class Seccion:
    codigo: str
    titulo: str
    que_es: str
    acciones: list
    consejos: list = field(default_factory=list)


CLINICOS_Y_ADMIN = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]


def _secciones():
    from alertas import permisos as al
    from antecedentes import permisos as an
    from citas import permisos as ci
    from cuidados import permisos as cu
    from examenes import permisos as ex
    from plan_atencion import permisos as pa
    from signos import permisos as si
    from valoracion import escalas as E
    from valoracion import permisos as va

    def roles_escala(codigo):
        return list(E.POR_CODIGO[codigo].roles)

    return [
        Seccion(
            'signos', 'Signos vitales',
            'Toma y registro de presión arterial, pulso, respiración, temperatura, saturación, glucometría, dolor y '
            'peso; balance de líquidos; y la eliminación (orina y deposición) que se anota en la nota de enfermería.',
            [
                ('Ver los signos vitales, las gráficas y la eliminación de cada residente', si.ROLES_VER),
                ('Registrar signos vitales y peso', si.ROLES_REGISTRO),
                ('Registrar líquidos (lo que recibe y lo que elimina)', si.ROLES_LIQUIDOS),
                ('Anular un registro propio dentro de las 24 horas siguientes, con motivo', si.ROLES_REGISTRO),
                ('Anular cualquier registro, en cualquier momento, con motivo', si.ROLES_ANULAR_SIEMPRE),
                ('Ajustar el rango normal de un residente (por ejemplo, la saturación meta en EPOC)', si.ROLES_RANGO_RESIDENTE),
                ('Cambiar los rangos generales que se usan para todos los residentes', si.ROLES_RANGO_HOGAR),
            ],
            ['Llene solo los signos que tomó; el color de cada casilla le indica si el valor está en rango.',
             'Un valor crítico genera de inmediato una alerta para el médico y el jefe de enfermería.',
             'La deposición y la diuresis se registran en la nota de enfermería (casillas sí/no).'],
        ),
        Seccion(
            'valoracion', 'Valoración geriátrica',
            'Escalas que miden cómo está el residente en lo funcional (Katz, Lawton), las caídas (Tinetti), la piel '
            '(Norton), la memoria (Pfeiffer) y el ánimo (Yesavage). Cada escala se repite con la frecuencia que exige el hogar.',
            [
                ('Ver los resultados, su evolución y qué escalas están vencidas', va.ROLES_VER),
                ('Aplicar Katz (actividades básicas)', roles_escala('katz')),
                ('Aplicar Lawton y Brody (actividades instrumentales)', roles_escala('lawton')),
                ('Aplicar Pfeiffer (memoria y orientación)', roles_escala('pfeiffer')),
                ('Aplicar Yesavage (estado de ánimo)', roles_escala('yesavage')),
                ('Aplicar Tinetti (equilibrio, marcha y riesgo de caídas)', roles_escala('tinetti')),
                ('Aplicar Norton (riesgo de lesiones por presión)', roles_escala('norton')),
                ('Anular una escala aplicada por usted el mismo día, con motivo', va.ROLES_APLICAR_ALGUNA),
                ('Anular cualquier escala, con motivo', va.ROLES_ANULAR_SIEMPRE),
                ('Definir qué escalas exige el hogar y cada cuántos meses', va.ROLES_CONFIGURAR),
            ],
            ['El puntaje se calcula solo mientras responde.',
             'Un resultado de riesgo (por ejemplo, riesgo alto de caídas) genera una alerta durante una semana.'],
        ),
        Seccion(
            'plan', 'Planes de atención',
            'El plan de cada residente: qué necesita, qué se quiere lograr y qué hace cada profesional para lograrlo. '
            'Se elabora en borrador entre el equipo, se activa y se le hace seguimiento hasta su revisión.',
            [
                ('Ver el plan vigente, sus objetivos, seguimientos y versiones anteriores', pa.ROLES_VER),
                ('Elaborar el plan en borrador: escribir la situación y agregar, corregir o quitar objetivos de su área', pa.ROLES_ELABORAR),
                ('Agregar un objetivo nuevo al plan vigente', pa.ROLES_ELABORAR),
                ('Activar el plan (lo vuelve vigente) y revisarlo (crea la versión siguiente)', pa.ROLES_ACTIVAR),
                ('Registrar el seguimiento de un objetivo (qué se observó y si se logró)', pa.ROLES_SEGUIMIENTO),
            ],
            ['Use los objetivos sugeridos: salen de las escalas y del peso, y los puede ajustar antes de guardarlos.',
             'En un plan vigente los objetivos no se editan: se registra seguimiento o se revisa el plan.'],
        ),
        Seccion(
            'ordenes', 'Órdenes médicas',
            'Las órdenes de medicamentos de cada residente, transcritas de la fórmula médica: medicamento, dosis, '
            'horarios o "si es necesario", fechas y foto de la fórmula.',
            [
                ('Ver las órdenes médicas y la foto de la fórmula', CLINICOS_Y_ADMIN),
                ('Imprimir la hoja de tratamiento (órdenes activas con las alergias)', CLINICOS_Y_ADMIN),
                ('Registrar una orden médica (transcribir la fórmula)', Rol.ROLES_REGISTRO_TRATAMIENTO),
                ('Suspender una orden médica, con motivo', Rol.ROLES_REGISTRO_TRATAMIENTO),
            ],
            ['Si el residente tiene una alergia registrada al medicamento, el sistema avisa y pide confirmación.'],
        ),
        Seccion(
            'suministro', 'Suministro de medicamentos',
            'La ronda de medicamentos en dos pasos: primero alistar (ver qué sacar de los cajones para la franja) y '
            'luego suministrar y registrar; y "Medicamentos de hoy" de cada residente.',
            [
                ('Ver la ronda (alistamiento), imprimir la lista de alistamiento y ver los medicamentos de hoy', CLINICOS_Y_ADMIN),
                ('Registrar que se suministró un medicamento (o que no se suministró, con el motivo)', Rol.ROLES_ADMINISTRACION),
                ('Suministrar del botiquín cuando el residente no tiene en su cajón', Rol.ROLES_ADMINISTRACION),
                ('Anular un suministro propio dentro de las 2 horas siguientes', Rol.ROLES_ADMINISTRACION),
                ('Anular cualquier suministro del día', [Rol.JEFE_ENFERMERIA]),
            ],
            ['Una toma que pasa de su hora sin registrarse genera una alerta para la auxiliar y el jefe.'],
        ),
        Seccion(
            'cajon', 'Cajón de medicamentos',
            'Los medicamentos que trae la familia o la EPS para un residente, por lote y fecha de vencimiento. '
            'El sistema suministra primero el lote que vence primero.',
            [
                ('Ver el cajón de un residente', CLINICOS_Y_ADMIN),
                ('Guardar en el cajón lo que trae la familia o la EPS', Rol.ROLES_INGRESO_MEDICAMENTO),
                ('Descartar un lote vencido o dañado, con motivo', Rol.ROLES_AJUSTE_INVENTARIO),
                ('Imprimir el acta de recepción de lo que se guardó en el cajón un día', CLINICOS_Y_ADMIN),
                ('Devolver medicamentos a la familia (egreso o suspensión) e imprimir el acta', Rol.ROLES_AJUSTE_INVENTARIO),
            ],
            ['Un lote vencido genera la alerta "El lote ### de [medicamento] se encuentra vencido"; se cierra al descartarlo.'],
        ),
        Seccion(
            'botiquin', 'Botiquín',
            'Medicamentos comprados por el hogar para emergencias o para prestar cuando un residente no tiene en su cajón.',
            [
                ('Ver el botiquín y los préstamos pendientes', Rol.ROLES_INGRESO_MEDICAMENTO),
                ('Agregar al botiquín', Rol.ROLES_INGRESO_MEDICAMENTO),
                ('Descartar un lote y marcar préstamos como repuestos', Rol.ROLES_AJUSTE_INVENTARIO),
                ('Ver los vencimientos de todos los cajones y del botiquín', Rol.ROLES_INGRESO_MEDICAMENTO),
                ('Cambiar los días del semáforo de vencimiento y las horas estándar', [Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA]),
            ],
            ['Cuando la familia repone un préstamo, agregue lo que trajo al botiquín y marque el préstamo como repuesto.'],
        ),
        Seccion(
            'historial_med', 'Historial de suministros y Kardex',
            'Todo lo que se ha suministrado o dejado de suministrar, con quién lo registró. El Kardex muestra el mes '
            'completo en una cuadrícula por medicamento, hora y día, listo para imprimir.',
            [
                ('Ver el historial y el Kardex de un residente o del hogar', CLINICOS_Y_ADMIN),
                ('Descargar el historial en Excel (CSV)', Rol.ROLES_EXPORTACION),
                ('Imprimir el Kardex del mes', CLINICOS_Y_ADMIN),
            ],
            ['En el Kardex, pase el cursor sobre una ✕ para ver por qué no se suministró.',
             'Un "?" es una toma que pasó sin registro: revísela con quien estaba de turno.'],
        ),
        Seccion(
            'cuidados', 'Cuidados del turno',
            'La planilla de cuidados diarios de todos los residentes: cambios de posición, cambio de pañal, baño, '
            'higiene oral y movilización. Cada residente muestra solo los cuidados de su plan.',
            [
                ('Ver la planilla y los cuidados de cada residente', cu.ROLES_VER),
                ('Registrar un cuidado con un toque (hora actual) o con otra hora y una observación', cu.ROLES_CUIDADOS),
                ('Definir el plan de cuidados de un residente (qué cuidados y cada cuánto)', cu.ROLES_PLAN),
                ('Anular un cuidado propio dentro de las 24 horas, con motivo', cu.ROLES_CUIDADOS),
                ('Anular cualquier cuidado, con motivo', cu.ROLES_ANULAR_SIEMPRE),
            ],
            ['El botón de cambio de posición propone la siguiente posición de la rotación (derecho, boca arriba, '
             'izquierdo, semisentado); la flecha muestra las demás.',
             'En amarillo aparece lo pendiente: el cambio de posición atrasado, el baño (más de 24 horas, o 48 si es '
             'día de por medio), la higiene oral (más de 12 horas) o el pañal sin cambio en 4 horas. Un cambio de posición atrasado genera una alerta.',
             'La diuresis y la deposición se siguen registrando en la nota de enfermería.',
             'Si la escala de Norton marca riesgo, el sistema sugiere los cambios de posición en el plan.'],
        ),
        Seccion(
            'heridas', 'Heridas y lesiones por presión',
            'Cada herida con su tipo, ubicación y estadio, y sus seguimientos: medidas, aspecto, curación hecha y foto. '
            'La gráfica muestra si el tamaño baja.',
            [
                ('Ver heridas, seguimientos y fotos', cu.ROLES_VER),
                ('Registrar una herida y sus seguimientos o curaciones', cu.ROLES_HERIDAS),
                ('Cerrar una herida (cicatrizó, egreso, fallecimiento o error)', cu.ROLES_CERRAR_HERIDA),
                ('Anular un seguimiento propio dentro de las 24 horas, con motivo', cu.ROLES_HERIDAS),
            ],
            ['Tome las fotos siempre a la misma distancia y con una regla al lado.',
             'Una lesión por presión que aparece en el hogar es un evento adverso: avisa al jefe de enfermería y al médico.',
             'Marcar signos de infección genera una alerta para el médico.'],
        ),
        Seccion(
            'examenes', 'Exámenes médicos',
            'Órdenes de laboratorio, imágenes y otros exámenes; sus resultados (archivo y valores) y la revisión del médico.',
            [
                ('Ver exámenes, resultados y la evolución de los laboratorios', CLINICOS_Y_ADMIN),
                ('Registrar una orden de examen', ex.ROLES_REGISTRO_EXAMENES),
                ('Subir el resultado, agregar información adicional o corregir un valor', ex.ROLES_REGISTRO_EXAMENES),
                ('Revisar el resultado y dejar la conducta', ex.ROLES_REVISION_EXAMENES),
            ],
            ['Un resultado con valores críticos genera una alerta crítica para el médico y el jefe de enfermería.'],
        ),
        Seccion(
            'citas', 'Citas médicas',
            'Citas fuera del hogar (especialistas, controles, exámenes, terapias): cuándo, dónde, cómo prepararlo, '
            'quién acompaña y cómo llega; y qué pasó en la cita.',
            [
                ('Ver la agenda y las citas de cada residente', ci.ROLES_VER),
                ('Agendar, corregir, reprogramar o cancelar una cita', ci.ROLES_REGISTRO),
                ('Registrar qué pasó en la cita y adjuntar la fórmula u orden', ci.ROLES_REGISTRO),
            ],
            ['El día anterior y el mismo día llega una alerta con la preparación; sube de importancia si falta definir transporte o acompañante.'],
        ),
        Seccion(
            'alertas', 'Alertas',
            'Avisos del sistema (por ejemplo, un examen crítico o un lote vencido) y avisos que publica el personal. '
            'Cada persona ve las alertas de sus roles.',
            [
                ('Ver y atender las alertas dirigidas a su rol', al.ROLES_PERSONAL),
                ('Ver todas las alertas del hogar', al.ROLES_VER_TODAS),
                ('Descartar una alerta que no aplica, con motivo', al.ROLES_DESCARTAR),
                ('Publicar un aviso para uno o varios roles', al.ROLES_AVISOS),
                ('Configurar qué alertas están activas y sus tiempos', al.ROLES_CONFIGURAR),
            ],
            ['Las alertas del sistema se cierran solas cuando se resuelve la situación.',
             'Para atender una alerta crítica hay que escribir qué se hizo.'],
        ),
        Seccion(
            'institucion', 'Institución',
            'Los departamentos (pabellones o pisos), habitaciones y camas del hogar, con el residente que ocupa '
            'cada cama. Sirve también para encontrar a un residente por su lugar y entrar a su expediente.',
            [
                ('Ver departamentos, habitaciones, camas y quién ocupa cada una; entrar al expediente desde la cama',
                 CLINICOS_Y_ADMIN),
                ('Crear y editar departamentos, habitaciones y camas', [Rol.ADMINISTRADOR]),
                ('Desactivar o reactivar un departamento, una habitación o una cama libre', [Rol.ADMINISTRADOR]),
            ],
            ['Use el buscador para encontrar a un residente o una cama.',
             'Al crear una habitación o una cama puede agregar el departamento o la habitación sin salir del formulario.',
             'No se puede desactivar nada que tenga una cama ocupada por un residente activo.'],
        ),
        Seccion(
            'antecedentes', 'Alergias y antecedentes',
            'Alergias (a medicamentos, alimentos u otras) y antecedentes de salud del residente. '
            '"Sin alergias conocidas" se declara explícitamente.',
            [
                ('Ver alergias y antecedentes', an.ROLES_REGISTRO),
                ('Registrar una alergia o un antecedente, o declarar "sin alergias conocidas"', an.ROLES_REGISTRO),
                ('Inactivar una alergia o un antecedente registrado por error, con motivo', an.ROLES_INACTIVACION),
            ],
            ['Las alergias aparecen en rojo en todas las pantallas del residente y se cruzan con las órdenes médicas.'],
        ),
    ]


# Qué sección corresponde a cada pantalla (por nombre de URL).
PANTALLAS = {
    'signos': ['signos_tablero', 'signos_residente', 'signos_control_crear', 'signos_liquidos_crear',
               'signos_rango_residente', 'signos_rangos_hogar'],
    'valoracion': ['valoracion_tablero', 'valoracion_residente', 'valoracion_aplicar', 'valoracion_detalle',
                   'valoracion_configuracion'],
    'plan': ['plan_tablero', 'plan_residente', 'plan_detalle', 'plan_editar', 'plan_objetivo_crear',
             'plan_objetivo_editar'],
    'ordenes': ['tratamiento_lista', 'tratamiento_crear', 'tratamiento_detalle', 'tratamiento_suspender', 'hoja_tratamiento'],
    'suministro': ['ronda', 'hoja_dia', 'administracion_registrar', 'administracion_no_registrar',
                   'administracion_prn_registrar', 'administracion_anular'],
    'cajon': ['ingreso_lista', 'ingreso_crear', 'medicamentos_devolver', 'acta_devolucion', 'acta_recepcion'],
    'botiquin': ['botiquin_lista', 'ingreso_botiquin_crear', 'vencimientos', 'medicamentos_configuracion'],
    'historial_med': ['historial_hogar', 'historial_residente', 'kardex'],
    'cuidados': ['cuidados_planilla', 'cuidados_residente', 'cuidados_plan'],
    'heridas': ['cuidados_heridas', 'cuidados_herida_crear', 'cuidados_herida_detalle', 'cuidados_seguimiento_crear'],
    'examenes': ['examenes_bandeja', 'examenes_residente', 'examen_crear', 'examenes_tendencias', 'examen_detalle',
                 'examen_editar', 'examen_resultado', 'examen_adenda', 'examen_revisar', 'examen_cancelar',
                 'valor_corregir'],
    'citas': ['citas_agenda', 'citas_residente', 'cita_crear', 'cita_detalle', 'cita_editar'],
    'alertas': ['alertas_bandeja', 'aviso_crear', 'alertas_configuracion'],
    'antecedentes': ['residente_antecedentes', 'alergia_crear', 'antecedente_crear'],
    'institucion': ['institucion', 'departamento_crear', 'departamento_editar', 'habitacion_crear',
                    'habitacion_editar', 'cama_crear', 'cama_editar'],
}
SECCION_POR_PANTALLA = {url: codigo for codigo, urls in PANTALLAS.items() for url in urls}


def seccion(codigo):
    return next((s for s in _secciones() if s.codigo == codigo), None)


def todas():
    return _secciones()


def para_usuario(sec, usuario):
    """Separa las acciones en las que el usuario puede hacer y las que no,
    con los nombres de los roles que sí pueden."""
    nombres = dict(Rol.ROLES)
    mis_roles = set(usuario.roles.values_list('nombre', flat=True))
    puede, no_puede = [], []
    for texto, roles in sec.acciones:
        roles = list(roles) if roles else []
        if not roles or mis_roles & set(roles):
            puede.append(texto)
        else:
            no_puede.append((texto, [nombres.get(r, r) for r in roles]))
    return puede, no_puede, [nombres.get(r, r) for r in sorted(mis_roles)]
