"""Reevaluación inmediata, acotada al residente, cuando se guarda un
registro que puede crear o cerrar alertas. Así un examen crítico avisa en
el momento y una toma registrada deja de alertar sin esperar al motor."""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .reglas import REGLAS_POR_MODELO

log = logging.getLogger(__name__)


def _programar(hogar, residente, grupo):
    if hogar is None:
        return

    def _correr():
        from .motor import evaluar_hogar
        try:
            evaluar_hogar(hogar, reglas=REGLAS_POR_MODELO[grupo], residente=residente)
        except Exception:  # noqa: BLE001
            log.exception('Falló la reevaluación de alertas (%s)', grupo)

    transaction.on_commit(_correr)


def _conectar():
    from antecedentes.models import Alergia, EstadoAlergias
    from citas.models import Cita
    from examenes.models import Examen
    from medicamentos.models import Administracion, IngresoMedicamento, Prescripcion
    from notas_clinicas.models import NotaClinica
    from signos.models import ControlSignos, RangoResidente, RangosHogar, RegistroLiquidos
    from valoracion.models import ConfiguracionValoracion, Valoracion

    @receiver(post_save, sender=Examen, weak=False, dispatch_uid='alertas_examen')
    def _examen(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'examen')

    @receiver(post_save, sender=IngresoMedicamento, weak=False, dispatch_uid='alertas_lote')
    def _lote(sender, instance, **kw):
        if instance.residente_id:
            _programar(instance.residente.hogar, instance.residente, 'lote')
        else:
            _programar(instance.hogar, None, 'lote')

    @receiver(post_save, sender=Administracion, weak=False, dispatch_uid='alertas_administracion')
    def _administracion(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'administracion')

    @receiver(post_save, sender=Prescripcion, weak=False, dispatch_uid='alertas_prescripcion')
    def _prescripcion(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'prescripcion')

    @receiver(post_save, sender=Alergia, weak=False, dispatch_uid='alertas_alergia')
    @receiver(post_save, sender=EstadoAlergias, weak=False, dispatch_uid='alertas_estado_alergias')
    def _alergias(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'alergias')

    @receiver(post_save, sender=Cita, weak=False, dispatch_uid='alertas_cita')
    def _cita(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'cita')

    @receiver(post_save, sender=ControlSignos, weak=False, dispatch_uid='alertas_signos')
    @receiver(post_save, sender=RangoResidente, weak=False, dispatch_uid='alertas_rango_residente')
    def _signos(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'signos')

    @receiver(post_save, sender=RangosHogar, weak=False, dispatch_uid='alertas_rangos_hogar')
    def _rangos_hogar(sender, instance, created=False, **kw):
        if not created:  # crear la fila con los valores por defecto no cambia nada
            _programar(instance.hogar, None, 'signos')

    @receiver(post_save, sender=RegistroLiquidos, weak=False, dispatch_uid='alertas_liquidos')
    def _liquidos(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'liquidos')

    @receiver(post_save, sender=NotaClinica, weak=False, dispatch_uid='alertas_nota')
    def _nota(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'nota')

    @receiver(post_save, sender=Valoracion, weak=False, dispatch_uid='alertas_valoracion')
    def _valoracion(sender, instance, **kw):
        _programar(instance.residente.hogar, instance.residente, 'valoracion')

    @receiver(post_save, sender=ConfiguracionValoracion, weak=False, dispatch_uid='alertas_conf_valoracion')
    def _conf_valoracion(sender, instance, created=False, **kw):
        if not created:
            _programar(instance.hogar, None, 'valoracion')


_conectar()
