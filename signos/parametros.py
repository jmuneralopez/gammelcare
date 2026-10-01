"""Parámetros de signos vitales y sus rangos por defecto para adultos
mayores. Cada hogar puede ajustar estos rangos y el médico puede fijar
rangos propios para un residente (por ejemplo, la saturación meta de un
paciente con EPOC o la presión meta de un hipertenso).

Cada rango tiene cuatro límites: crítico bajo < bajo (mínimo normal) …
máximo normal < crítico alto. Cualquiera puede quedar vacío.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Parametro:
    codigo: str
    nombre: str
    corto: str
    unidad: str
    decimales: int
    minimo_posible: Decimal
    maximo_posible: Decimal
    critico_min: object
    normal_min: object
    normal_max: object
    critico_max: object


def D(v):
    return None if v is None else Decimal(str(v))


PARAMETROS = [
    Parametro('pas', 'Presión arterial sistólica', 'PAS', 'mmHg', 0, D(40), D(300), D(80), D(90), D(150), D(180)),
    Parametro('pad', 'Presión arterial diastólica', 'PAD', 'mmHg', 0, D(20), D(200), D(40), D(50), D(90), D(110)),
    Parametro('fc', 'Frecuencia cardiaca', 'FC', 'lpm', 0, D(20), D(250), D(45), D(55), D(100), D(120)),
    Parametro('fr', 'Frecuencia respiratoria', 'FR', 'rpm', 0, D(4), D(70), D(8), D(12), D(22), D(30)),
    Parametro('temperatura', 'Temperatura', 'T°', '°C', 1, D(30), D(43), D('35.0'), D('35.5'), D('37.5'), D('38.5')),
    Parametro('spo2', 'Saturación de oxígeno', 'SpO₂', '%', 0, D(50), D(100), D(88), D(92), None, None),
    Parametro('glucometria', 'Glucometría', 'Glucosa', 'mg/dL', 0, D(10), D(800), D(54), D(70), D(180), D(300)),
    Parametro('dolor', 'Dolor (escala 0 a 10)', 'Dolor', '/10', 0, D(0), D(10), None, None, D(3), D(7)),
]
POR_CODIGO = {p.codigo: p for p in PARAMETROS}
CODIGOS = [p.codigo for p in PARAMETROS]

CRITICO_BAJO = 'critico_bajo'
BAJO = 'bajo'
NORMAL = 'normal'
ALTO = 'alto'
CRITICO_ALTO = 'critico_alto'
ETIQUETAS = {
    CRITICO_BAJO: 'Crítico bajo', BAJO: 'Bajo', NORMAL: 'Normal', ALTO: 'Alto', CRITICO_ALTO: 'Crítico alto',
}


def rango_por_defecto(codigo):
    p = POR_CODIGO[codigo]
    return {'critico_min': p.critico_min, 'normal_min': p.normal_min,
            'normal_max': p.normal_max, 'critico_max': p.critico_max}


def interpretar(valor, rango):
    if valor is None:
        return None
    if rango.get('critico_min') is not None and valor < rango['critico_min']:
        return CRITICO_BAJO
    if rango.get('critico_max') is not None and valor > rango['critico_max']:
        return CRITICO_ALTO
    if rango.get('normal_min') is not None and valor < rango['normal_min']:
        return BAJO
    if rango.get('normal_max') is not None and valor > rango['normal_max']:
        return ALTO
    return NORMAL


def es_critico(interpretacion):
    return interpretacion in (CRITICO_BAJO, CRITICO_ALTO)


def fuera_de_rango(interpretacion):
    return interpretacion not in (None, NORMAL)


def texto_rango(rango, decimales=0):
    def f(v):
        return '—' if v is None else (f'{v:.{decimales}f}')
    mn, mx = rango.get('normal_min'), rango.get('normal_max')
    if mn is not None and mx is not None:
        return f'{f(mn)} a {f(mx)}'
    if mn is not None:
        return f'≥ {f(mn)}'
    if mx is not None:
        return f'≤ {f(mx)}'
    return 'sin rango'
