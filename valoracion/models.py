"""Resultados de las escalas de valoración geriátrica.

Cada aplicación de una escala es un registro inmutable (con huella
SHA-256): respuestas, puntaje, interpretación, quién la aplicó y cuándo.
Un error se corrige anulando con motivo y aplicando de nuevo.
"""
import hashlib
import json

from django.conf import settings
from django.db import models
from django.utils import timezone

from hogares.models import Hogar
from residentes.models import Residente

from . import escalas as E


class Valoracion(models.Model):
    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='valoraciones')
    escala = models.CharField(max_length=20, choices=[(e.codigo, e.nombre) for e in E.ESCALAS])
    fecha = models.DateField('Fecha de aplicación', default=timezone.localdate)
    respuestas = models.JSONField(default=dict, blank=True)
    educacion = models.CharField(max_length=10, blank=True)
    puntaje = models.SmallIntegerField()
    interpretacion = models.CharField(max_length=120)
    nivel = models.CharField(max_length=10)
    observaciones = models.TextField('Observaciones', blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)
    hash_integridad = models.CharField(max_length=64, editable=False, blank=True)

    anulada = models.BooleanField(default=False)
    motivo_anulacion = models.TextField(blank=True)
    anulada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+')
    fecha_anulacion = models.DateTimeField(null=True, blank=True)

    CAMPOS_ANULACION = {'anulada', 'motivo_anulacion', 'anulada_por', 'fecha_anulacion'}

    class Meta:
        ordering = ['-fecha', '-fecha_registro']
        verbose_name = 'Valoración'
        verbose_name_plural = 'Valoraciones'
        indexes = [models.Index(fields=['residente', 'escala', 'fecha'])]

    def __str__(self):
        return f'{self.definicion.corto} {self.puntaje} — {self.fecha:%d/%m/%Y}'

    @property
    def definicion(self):
        return E.POR_CODIGO[self.escala]

    @property
    def banda(self):
        return self.definicion.interpretar(self.puntaje)

    def calcular_hash(self):
        partes = [str(self.residente_id), self.escala, self.fecha.isoformat(),
                  json.dumps(self.respuestas, sort_keys=True), self.educacion, str(self.puntaje),
                  self.observaciones, str(self.registrado_por_id)]
        return hashlib.sha256('|'.join(partes).encode('utf-8')).hexdigest()

    def verificar_integridad(self):
        return self.hash_integridad == self.calcular_hash()

    def save(self, *args, **kwargs):
        if not self.pk:
            self.hash_integridad = self.calcular_hash()
        else:
            campos = kwargs.get('update_fields')
            if not campos or not set(campos) <= self.CAMPOS_ANULACION:
                raise ValueError('Las valoraciones no se modifican: se anulan con motivo y se aplican de nuevo.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Las valoraciones no se eliminan: se anulan con motivo.')

    def anular(self, usuario, motivo):
        self.anulada = True
        self.motivo_anulacion = motivo
        self.anulada_por = usuario
        self.fecha_anulacion = timezone.now()
        self.save(update_fields=list(self.CAMPOS_ANULACION))

    def respuestas_legibles(self):
        """[(grupo, pregunta, texto de la opción elegida, puntos)] para mostrar."""
        filas = []
        for item in self.definicion.items:
            valor = self.respuestas.get(item.codigo)
            texto = ''
            if isinstance(valor, dict):
                texto, valor = valor.get('texto', ''), valor.get('puntos')
            filas.append((item.grupo, item.pregunta, texto, valor))
        return filas


class ConfiguracionValoracion(models.Model):
    """Cada cuántos meses exige el hogar cada escala (0 = no exigida)."""
    hogar = models.OneToOneField(Hogar, on_delete=models.CASCADE, related_name='configuracion_valoracion')
    periodicidad = models.JSONField(default=dict, blank=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='+')
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración de valoración geriátrica'
        verbose_name_plural = 'Configuraciones de valoración geriátrica'

    @classmethod
    def para_hogar(cls, hogar):
        obj, _ = cls.objects.get_or_create(hogar=hogar)
        return obj

    def meses(self, codigo):
        valor = (self.periodicidad or {}).get(codigo)
        return int(valor) if valor not in (None, '') else E.POR_CODIGO[codigo].periodicidad_meses

    def exigidas(self):
        return [e for e in E.ESCALAS if self.meses(e.codigo) > 0]
