"""Definición de las escalas de la valoración geriátrica integral.

Solo escalas de uso libre, que no exigen licencia para usarlas en un
software comercial (decisión de Juan Carlos, 2026-10-01): Katz, Lawton y
Brody, Pfeiffer, Yesavage (GDS-15), Tinetti y Norton. Todas se aplican
completas en pantalla, ítem por ítem, y el sistema suma.

Quedan fuera por derechos de autor: Barthel (su publicación original solo
autoriza el uso libre no comercial), Minimental (MMSE), Braden, MNA y
Zarit. Katz reemplaza a Barthel para las actividades básicas, Norton a
Braden para el riesgo de lesiones por presión; el estado nutricional se
vigila con el peso (alerta de pérdida en signos vitales).

Cada escala trae sus bandas de interpretación (de menor a mayor puntaje)
con un nivel de color: 'ok', 'leve', 'moderado', 'grave'. `alerta=True`
marca la banda que debe generar una alerta al registrarse.
"""
from dataclasses import dataclass, field

from usuarios.models import Rol

OK, LEVE, MODERADO, GRAVE = 'ok', 'leve', 'moderado', 'grave'


@dataclass(frozen=True)
class Banda:
    minimo: int
    maximo: int
    texto: str
    nivel: str
    alerta: bool = False


@dataclass(frozen=True)
class Item:
    codigo: str
    pregunta: str
    opciones: tuple  # ((puntos, texto), ...)
    grupo: str = ''


@dataclass(frozen=True)
class Escala:
    codigo: str
    nombre: str
    corto: str
    dominio: str
    que_mide: str
    modo: str  # siempre 'items' (se conserva por si en el futuro se registra solo el puntaje)
    minimo: int
    maximo: int
    bandas: tuple
    roles: tuple
    items: tuple = ()
    instrucciones: str = ''
    periodicidad_meses: int = 6  # sugerida; 0 = no exigida por defecto
    cuenta_errores: bool = False  # Pfeiffer: el puntaje es el número de errores
    deterioro_alerta: int = 0  # caída de puntos frente a la anterior que genera alerta
    mayor_es_mejor: bool = True
    extra: dict = field(default_factory=dict)

    def interpretar(self, puntaje):
        for b in self.bandas:
            if b.minimo <= puntaje <= b.maximo:
                return b
        return None


SI_NO = ((1, 'Sí'), (0, 'No'))
NO_SI = ((0, 'Sí'), (1, 'No'))

# ── Katz ────────────────────────────────────────────────────────────
KATZ = Escala(
    codigo='katz', nombre='Índice de Katz', corto='Katz', dominio='Funcional',
    que_mide='Actividades básicas de la vida diaria: bañarse, vestirse, uso del sanitario, trasladarse, continencia y alimentarse.',
    modo='items', minimo=0, maximo=6, periodicidad_meses=6, deterioro_alerta=2,
    roles=(Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO, Rol.FISIOTERAPEUTA, Rol.TERAPEUTA_OCUPACIONAL),
    instrucciones='Marque lo que el residente HACE habitualmente, según observación directa y lo que informa el personal. Independiente = sin supervisión, dirección ni ayuda de otra persona.',
    items=(
        Item('banarse', 'Bañarse', ((1, 'Independiente: se baña solo, o solo necesita ayuda en una parte (espalda, zona genital o una extremidad)'),
                                    (0, 'Dependiente: necesita ayuda para bañar más de una parte, para entrar o salir de la ducha, o hay que bañarlo'))),
        Item('vestirse', 'Vestirse', ((1, 'Independiente: saca la ropa y se viste solo, incluidos botones y cremalleras (puede necesitar ayuda para atarse los zapatos)'),
                                      (0, 'Dependiente: necesita ayuda para vestirse o hay que vestirlo'))),
        Item('sanitario', 'Uso del sanitario', ((1, 'Independiente: va al sanitario, se sienta, se levanta, se arregla la ropa y se limpia solo'),
                                                (0, 'Dependiente: necesita ayuda para ir o usar el sanitario, o usa pato o bacinilla'))),
        Item('trasladarse', 'Trasladarse', ((1, 'Independiente: entra y sale de la cama o la silla solo (puede usar ayudas como caminador o barandas)'),
                                            (0, 'Dependiente: necesita ayuda para pasar de la cama a la silla, o hay que trasladarlo'))),
        Item('continencia', 'Continencia', ((1, 'Independiente: controla completamente la orina y la deposición'),
                                            (0, 'Dependiente: incontinencia urinaria o fecal, parcial o total'))),
        Item('alimentarse', 'Alimentarse', ((1, 'Independiente: lleva la comida del plato a la boca solo (otra persona puede servirla o picarla)'),
                                            (0, 'Dependiente: necesita ayuda parcial o total para comer, o se alimenta por sonda'))),
    ),
    bandas=(Banda(0, 2, 'Dependencia grave', GRAVE, alerta=True), Banda(3, 4, 'Dependencia moderada', MODERADO),
            Banda(5, 5, 'Dependencia leve', LEVE), Banda(6, 6, 'Independiente', OK)),
)

# ── Lawton y Brody ──────────────────────────────────────────────────
LAWTON = Escala(
    codigo='lawton', nombre='Escala de Lawton y Brody', corto='Lawton', dominio='Funcional',
    que_mide='Actividades instrumentales (teléfono, compras, comida, casa, ropa, transporte, medicación, dinero).',
    modo='items', minimo=0, maximo=8, periodicidad_meses=0,
    roles=(Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.TERAPEUTA_OCUPACIONAL, Rol.TRABAJO_SOCIAL),
    instrucciones='Elija la frase que mejor describe lo que hace el residente. En un hogar muchas tareas las hace el personal: puntúe la capacidad que conserva.',
    items=(
        Item('telefono', 'Uso del teléfono', ((1, 'Lo usa por iniciativa propia, busca y marca números'),
                                              (1, 'Marca unos pocos números bien conocidos'),
                                              (1, 'Contesta, pero no marca'), (0, 'No lo usa'))),
        Item('compras', 'Hacer compras', ((1, 'Hace todas las compras necesarias solo'), (0, 'Hace solo pequeñas compras'),
                                          (0, 'Necesita ir acompañado'), (0, 'Totalmente incapaz'))),
        Item('comida', 'Preparación de la comida', ((1, 'Organiza, prepara y sirve comidas adecuadas solo'),
                                                     (0, 'Prepara comidas si le dan los ingredientes'),
                                                     (0, 'Calienta y sirve, pero no sigue una dieta adecuada'),
                                                     (0, 'Necesita que le preparen y sirvan'))),
        Item('casa', 'Cuidado de la casa', ((1, 'Mantiene la casa solo o con ayuda ocasional'),
                                            (1, 'Hace tareas ligeras (lavar platos, tender la cama)'),
                                            (1, 'Hace tareas ligeras, pero no mantiene un nivel de limpieza aceptable'),
                                            (1, 'Necesita ayuda en todas las tareas'), (0, 'No participa'))),
        Item('ropa', 'Lavado de la ropa', ((1, 'Lava toda su ropa solo'), (1, 'Lava solo prendas pequeñas'),
                                           (0, 'Otra persona lava toda su ropa'))),
        Item('transporte', 'Uso de medios de transporte', ((1, 'Viaja solo en transporte público o conduce'),
                                                           (1, 'Toma taxi solo, pero no otro transporte'),
                                                           (1, 'Viaja en transporte público acompañado'),
                                                           (0, 'Solo en taxi o carro con ayuda'), (0, 'No viaja'))),
        Item('medicacion', 'Responsabilidad sobre su medicación', ((1, 'Toma su medicación a la hora y dosis correctas'),
                                                                    (0, 'La toma si se la preparan antes'),
                                                                    (0, 'No es capaz'))),
        Item('dinero', 'Manejo del dinero', ((1, 'Se encarga de sus asuntos económicos solo'),
                                             (1, 'Maneja gastos diarios, pero necesita ayuda con el banco y compras grandes'),
                                             (0, 'Incapaz de manejar dinero'))),
    ),
    bandas=(Banda(0, 1, 'Dependencia total', GRAVE), Banda(2, 3, 'Dependencia grave', GRAVE),
            Banda(4, 5, 'Dependencia moderada', MODERADO), Banda(6, 7, 'Dependencia leve', LEVE),
            Banda(8, 8, 'Independiente', OK)),
)

# ── Pfeiffer ────────────────────────────────────────────────────────
PFEIFFER = Escala(
    codigo='pfeiffer', nombre='Cuestionario de Pfeiffer (SPMSQ)', corto='Pfeiffer', dominio='Cognitivo',
    que_mide='Tamizaje de deterioro cognitivo (orientación, memoria, cálculo). Cuenta errores.',
    modo='items', minimo=0, maximo=10, periodicidad_meses=6, cuenta_errores=True, mayor_es_mejor=False,
    roles=(Rol.MEDICO, Rol.PSICOLOGO, Rol.TERAPEUTA_OCUPACIONAL, Rol.JEFE_ENFERMERIA),
    instrucciones='Haga las preguntas tal cual y marque si la respuesta fue correcta. Verifique con el expediente los datos personales. Indique abajo el nivel educativo: el sistema ajusta el resultado.',
    items=tuple(Item(c, p, ((0, 'Correcta'), (1, 'Error'))) for c, p in (
        ('fecha', '¿Qué fecha es hoy? (día, mes y año)'),
        ('dia_semana', '¿Qué día de la semana es hoy?'),
        ('lugar', '¿Cómo se llama este lugar?'),
        ('telefono', '¿Cuál es su número de teléfono? (si no tiene: ¿cuál es su dirección?)'),
        ('edad', '¿Cuántos años tiene?'),
        ('nacimiento', '¿Cuál es la fecha de su nacimiento?'),
        ('presidente', '¿Quién es el presidente actual del país?'),
        ('presidente_anterior', '¿Quién fue el presidente anterior?'),
        ('apellidos_madre', '¿Cuáles son los dos apellidos de su mamá?'),
        ('restas', 'Reste de 3 en 3 a partir de 20 (cualquier error en la serie cuenta como error)'),
    )),
    bandas=(Banda(0, 2, 'Sin deterioro cognitivo', OK), Banda(3, 4, 'Deterioro cognitivo leve', LEVE),
            Banda(5, 7, 'Deterioro cognitivo moderado', MODERADO, alerta=True),
            Banda(8, 10, 'Deterioro cognitivo grave', GRAVE, alerta=True)),
    extra={'educacion': (('basica', 'Sin estudios o primaria incompleta (se permite un error más)', -1),
                         ('media', 'Primaria completa o bachillerato', 0),
                         ('superior', 'Estudios superiores (se permite un error menos)', 1))},
)

# ── Yesavage GDS-15 ─────────────────────────────────────────────────
_GDS = (
    ('satisfecho', '¿Está básicamente satisfecho con su vida?', NO_SI),
    ('renuncio', '¿Ha dejado muchas de sus actividades e intereses?', SI_NO),
    ('vacia', '¿Siente que su vida está vacía?', SI_NO),
    ('aburrido', '¿Se aburre a menudo?', SI_NO),
    ('animo', '¿Está de buen ánimo la mayor parte del tiempo?', NO_SI),
    ('miedo', '¿Tiene miedo de que algo malo le vaya a pasar?', SI_NO),
    ('feliz', '¿Se siente feliz la mayor parte del tiempo?', NO_SI),
    ('desamparado', '¿Se siente a menudo desamparado?', SI_NO),
    ('casa', '¿Prefiere quedarse en su cuarto en lugar de salir y hacer cosas nuevas?', SI_NO),
    ('memoria', '¿Siente que tiene más problemas de memoria que la mayoría?', SI_NO),
    ('vivo', '¿Piensa que es maravilloso estar vivo?', NO_SI),
    ('inutil', '¿Se siente inútil tal como está ahora?', SI_NO),
    ('energia', '¿Se siente lleno de energía?', NO_SI),
    ('desesperada', '¿Siente que su situación no tiene esperanza?', SI_NO),
    ('mejor', '¿Cree que la mayoría de la gente está mejor que usted?', SI_NO),
)
YESAVAGE = Escala(
    codigo='yesavage', nombre='Escala de depresión geriátrica de Yesavage (GDS-15)', corto='Yesavage', dominio='Afectivo',
    que_mide='Tamizaje de síntomas depresivos en adultos mayores.',
    modo='items', minimo=0, maximo=15, periodicidad_meses=6, mayor_es_mejor=False,
    roles=(Rol.MEDICO, Rol.PSICOLOGO, Rol.JEFE_ENFERMERIA),
    instrucciones='Pregunte cómo se ha sentido en la última semana. No es válida si el residente tiene deterioro cognitivo moderado o grave (Pfeiffer 5 o más errores).',
    items=tuple(Item(c, p, o) for c, p, o in _GDS),
    bandas=(Banda(0, 5, 'Normal', OK), Banda(6, 9, 'Probable depresión', MODERADO, alerta=True),
            Banda(10, 15, 'Depresión establecida', GRAVE, alerta=True)),
)

# ── Tinetti ─────────────────────────────────────────────────────────
TINETTI = Escala(
    codigo='tinetti', nombre='Escala de Tinetti (equilibrio y marcha)', corto='Tinetti', dominio='Movilidad y caídas',
    que_mide='Equilibrio (16 puntos) y marcha (12 puntos); estima el riesgo de caídas.',
    modo='items', minimo=0, maximo=28, periodicidad_meses=6, deterioro_alerta=4,
    roles=(Rol.MEDICO, Rol.FISIOTERAPEUTA, Rol.JEFE_ENFERMERIA),
    instrucciones='Silla dura sin brazos. Para la marcha, el residente camina unos 3 metros a paso normal y vuelve, con su ayuda habitual (bastón o caminador).',
    items=(
        Item('eq_sentado', 'Equilibrio sentado', ((0, 'Se inclina o se desliza en la silla'), (1, 'Se mantiene seguro')), 'Equilibrio'),
        Item('eq_levantarse', 'Levantarse', ((0, 'Imposible sin ayuda'), (1, 'Capaz, pero usa los brazos'),
                                             (2, 'Capaz sin usar los brazos')), 'Equilibrio'),
        Item('eq_intentos', 'Intentos para levantarse', ((0, 'Incapaz sin ayuda'), (1, 'Capaz, pero necesita más de un intento'),
                                                         (2, 'Capaz en un solo intento')), 'Equilibrio'),
        Item('eq_inmediato', 'Equilibrio inmediato al levantarse (primeros 5 segundos)',
             ((0, 'Inestable (se tambalea, mueve los pies, balancea el tronco)'),
              (1, 'Estable, pero usa caminador, bastón o se agarra'), (2, 'Estable sin apoyo')), 'Equilibrio'),
        Item('eq_pie', 'Equilibrio de pie', ((0, 'Inestable'), (1, 'Estable con los pies separados (más de 10 cm) o con apoyo'),
                                             (2, 'Estable con los pies juntos sin apoyo')), 'Equilibrio'),
        Item('eq_empujon', 'Empujón (pies juntos; el examinador empuja suave el esternón 3 veces)',
             ((0, 'Empieza a caerse'), (1, 'Se tambalea y se agarra, pero se mantiene'), (2, 'Estable')), 'Equilibrio'),
        Item('eq_ojos', 'Ojos cerrados (en la posición anterior)', ((0, 'Inestable'), (1, 'Estable')), 'Equilibrio'),
        Item('eq_giro_pasos', 'Giro de 360°: pasos', ((0, 'Pasos discontinuos'), (1, 'Pasos continuos')), 'Equilibrio'),
        Item('eq_giro_estab', 'Giro de 360°: estabilidad', ((0, 'Inestable (se tambalea o se agarra)'), (1, 'Estable')), 'Equilibrio'),
        Item('eq_sentarse', 'Sentarse', ((0, 'Inseguro (calcula mal la distancia, cae en la silla)'),
                                         (1, 'Usa los brazos o el movimiento es brusco'), (2, 'Seguro, movimiento suave')), 'Equilibrio'),
        Item('ma_inicio', 'Inicio de la marcha (después de decirle "camine")', ((0, 'Duda o necesita varios intentos'),
                                                                                 (1, 'Sin vacilación')), 'Marcha'),
        Item('ma_der_long', 'Pie derecho: longitud del paso', ((0, 'No sobrepasa el pie izquierdo'), (1, 'Sobrepasa el pie izquierdo')), 'Marcha'),
        Item('ma_der_alt', 'Pie derecho: altura del paso', ((0, 'No se separa completamente del piso'), (1, 'Se separa completamente')), 'Marcha'),
        Item('ma_izq_long', 'Pie izquierdo: longitud del paso', ((0, 'No sobrepasa el pie derecho'), (1, 'Sobrepasa el pie derecho')), 'Marcha'),
        Item('ma_izq_alt', 'Pie izquierdo: altura del paso', ((0, 'No se separa completamente del piso'), (1, 'Se separa completamente')), 'Marcha'),
        Item('ma_simetria', 'Simetría del paso', ((0, 'Pasos de longitud desigual'), (1, 'Pasos iguales')), 'Marcha'),
        Item('ma_continuidad', 'Continuidad de los pasos', ((0, 'Se detiene o los pasos son discontinuos'), (1, 'Pasos continuos')), 'Marcha'),
        Item('ma_trayectoria', 'Trayectoria (observar unos 3 metros)', ((0, 'Desviación marcada'),
                                                                         (1, 'Desviación leve o usa ayuda'),
                                                                         (2, 'Recta sin ayuda')), 'Marcha'),
        Item('ma_tronco', 'Tronco', ((0, 'Balanceo marcado o usa ayuda'),
                                     (1, 'No se balancea, pero flexiona rodillas o espalda, o separa los brazos'),
                                     (2, 'No se balancea, no flexiona, no usa los brazos ni ayuda')), 'Marcha'),
        Item('ma_postura', 'Postura al caminar', ((0, 'Talones separados'), (1, 'Talones casi se tocan al caminar')), 'Marcha'),
    ),
    bandas=(Banda(0, 18, 'Riesgo alto de caídas', GRAVE, alerta=True), Banda(19, 24, 'Riesgo de caídas', MODERADO),
            Banda(25, 28, 'Riesgo bajo de caídas', OK)),
)

# ── Norton ──────────────────────────────────────────────────────────
NORTON = Escala(
    codigo='norton', nombre='Escala de Norton', corto='Norton', dominio='Piel (lesiones por presión)',
    que_mide='Riesgo de lesiones por presión (úlceras por presión).',
    modo='items', minimo=5, maximo=20, periodicidad_meses=3,
    roles=(Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO),
    instrucciones='Repítala si cambia el estado del residente (hospitalización, encamamiento, fiebre, incontinencia nueva).',
    items=(
        Item('fisico', 'Estado físico general', ((4, 'Bueno'), (3, 'Aceptable'), (2, 'Regular / pobre'), (1, 'Muy malo'))),
        Item('mental', 'Estado mental', ((4, 'Alerta'), (3, 'Apático'), (2, 'Confuso'), (1, 'Estuporoso o comatoso'))),
        Item('actividad', 'Actividad', ((4, 'Camina solo'), (3, 'Camina con ayuda'), (2, 'En silla de ruedas'), (1, 'En cama'))),
        Item('movilidad', 'Movilidad', ((4, 'Total'), (3, 'Disminuida'), (2, 'Muy limitada'), (1, 'Inmóvil'))),
        Item('incontinencia', 'Incontinencia', ((4, 'Ninguna'), (3, 'Ocasional'), (2, 'Urinaria o fecal'), (1, 'Urinaria y fecal'))),
    ),
    bandas=(Banda(5, 9, 'Riesgo muy alto de lesiones por presión', GRAVE, alerta=True),
            Banda(10, 12, 'Riesgo alto de lesiones por presión', GRAVE, alerta=True),
            Banda(13, 14, 'Riesgo medio', MODERADO), Banda(15, 20, 'Riesgo mínimo', OK)),
)

ESCALAS = [KATZ, LAWTON, PFEIFFER, YESAVAGE, TINETTI, NORTON]
POR_CODIGO = {e.codigo: e for e in ESCALAS}
CODIGOS = [e.codigo for e in ESCALAS]


def calcular(escala, respuestas, educacion='media'):
    """Puntaje a partir de las respuestas {codigo_item: puntos}. En Pfeiffer
    devuelve los errores ajustados por nivel educativo (sin bajar de 0 ni
    pasar de 10)."""
    total = sum(int(respuestas[i.codigo]) for i in escala.items)
    if escala.cuenta_errores:
        ajuste = {c: a for c, _t, a in escala.extra['educacion']}.get(educacion, 0)
        total = max(escala.minimo, min(escala.maximo, total + ajuste))
    return total
