"""Objetivos sugeridos a partir de lo que ya está registrado del residente
(escalas de valoración y signos vitales). Son solo un punto de partida: el
profesional los revisa y ajusta antes de agregarlos."""
from dataclasses import dataclass

from usuarios.models import Rol


@dataclass
class Sugerencia:
    clave: str
    area: str
    origen: str
    necesidad: str
    meta: str
    intervenciones: str
    responsable: str
    frecuencia: str = ''


def sugerencias(residente):
    from signos import services as sv
    from valoracion import escalas as E
    from valoracion import services as vs

    ultimas = {f['escala'].codigo: f['ultima'] for f in vs.estado_por_escala(residente) if f['ultima']}
    salida = []

    def nivel(codigo, *niveles):
        v = ultimas.get(codigo)
        return v if v and v.nivel in niveles else None

    if v := nivel('tinetti', E.GRAVE, E.MODERADO):
        salida.append(Sugerencia(
            'caidas', 'caidas', f'Tinetti {v.puntaje} ({v.interpretacion})',
            f'Riesgo de caídas: Tinetti {v.puntaje}/28 el {v.fecha:%d/%m/%Y}.',
            'Que el residente no presente caídas durante la vigencia del plan.',
            'Acompañar en desplazamientos; calzado cerrado y antideslizante; cama baja con barandas según criterio; '
            'iluminación nocturna y timbre a mano; ejercicios de equilibrio y fortalecimiento; revisar medicamentos que causan mareo.',
            Rol.FISIOTERAPEUTA, 'Ejercicios 3 veces por semana; medidas de seguridad todos los días'))
    if v := nivel('norton', E.GRAVE, E.MODERADO):
        salida.append(Sugerencia(
            'piel', 'piel', f'Norton {v.puntaje} ({v.interpretacion})',
            f'Riesgo de lesiones por presión: Norton {v.puntaje} el {v.fecha:%d/%m/%Y}.',
            'Mantener la piel íntegra, sin lesiones por presión.',
            'Cambios de posición cada 2 horas si está en cama; colchón o cojín de alivio de presión; revisar la piel en cada '
            'cambio de pañal y en el baño; hidratar la piel; mantenerla limpia y seca.',
            Rol.JEFE_ENFERMERIA, 'Cada 2 horas en cama; revisión de piel diaria'))
    if v := nivel('katz', E.GRAVE, E.MODERADO, E.LEVE):
        salida.append(Sugerencia(
            'funcional', 'funcional', f'Katz {v.puntaje} ({v.interpretacion})',
            f'{v.interpretacion} para las actividades básicas: Katz {v.puntaje}/6 el {v.fecha:%d/%m/%Y}.',
            'Conservar (o mejorar) la independencia en las actividades que aún realiza.',
            'Dejar que haga por sí mismo lo que puede, con supervisión; ayudar solo en lo que no logra; '
            'terapia ocupacional o física para entrenar actividades básicas.',
            Rol.TERAPEUTA_OCUPACIONAL, 'Diario en las rutinas; terapia 2 a 3 veces por semana'))
    if v := nivel('pfeiffer', E.LEVE, E.MODERADO, E.GRAVE):
        salida.append(Sugerencia(
            'cognitivo', 'cognitivo', f'Pfeiffer {v.puntaje} errores ({v.interpretacion})',
            f'{v.interpretacion}: Pfeiffer {v.puntaje} errores el {v.fecha:%d/%m/%Y}.',
            'Mantener la orientación y las capacidades cognitivas; prevenir episodios de confusión.',
            'Orientación diaria en tiempo y lugar (reloj, calendario visibles); estimulación cognitiva; rutinas estables; '
            'avisar al médico cambios bruscos de conducta o confusión.',
            Rol.TERAPEUTA_OCUPACIONAL, 'Estimulación cognitiva 3 veces por semana'))
    if v := nivel('yesavage', E.MODERADO, E.GRAVE):
        salida.append(Sugerencia(
            'afectivo', 'afectivo', f'Yesavage {v.puntaje} ({v.interpretacion})',
            f'{v.interpretacion}: Yesavage {v.puntaje}/15 el {v.fecha:%d/%m/%Y}.',
            'Mejorar el estado de ánimo y la participación en actividades.',
            'Valoración por psicología y por el médico; actividades que le gusten; favorecer visitas y contacto con la familia; '
            'vigilar apetito, sueño y aislamiento.',
            Rol.PSICOLOGO, 'Psicología semanal; actividades diarias'))
    cambio = sv.cambio_de_peso(residente, dias=30)
    if cambio and cambio[2] <= -5:
        actual, ref, pct = cambio
        salida.append(Sugerencia(
            'peso', 'nutricion', f'Pérdida de peso {abs(pct):.1f} %',
            f'Perdió {abs(pct):.1f} % de su peso en 30 días ({ref.peso} → {actual.peso} kg).',
            'Detener la pérdida de peso y recuperar el peso habitual.',
            'Valoración por nutrición; registrar cuánto come en cada comida; suplemento según indicación; '
            'pesar cada semana; revisar dentadura y dificultad para tragar.',
            Rol.NUTRICIONISTA, 'Peso semanal; registro de ingesta diario'))
    return salida
