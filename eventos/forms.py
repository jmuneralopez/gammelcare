from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import CAIDA, LPP, MEDICACION, ConfiguracionEventos, EventoAdverso, VigilanciaEvento

FMT = '%Y-%m-%dT%H:%M'


def _texto(filas=3, ejemplo=''):
    return forms.Textarea(attrs={'class': 'form-control', 'rows': filas, 'placeholder': ejemplo})


class EventoForm(forms.ModelForm):
    anonimo = forms.BooleanField(label='Reportar sin mi nombre', required=False,
                                 widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    class Meta:
        model = EventoAdverso
        fields = ['tipo', 'fecha_hora', 'lugar', 'lugar_detalle', 'descripcion', 'testigo', 'accion_inmediata',
                  'gravedad', 'aviso_medico', 'aviso_familia', 'aviso_familia_quien',
                  'golpe_cabeza', 'perdida_conciencia', 'anticoagulantes', 'lesiones',
                  'tipo_error', 'prescripcion', 'herida']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'fecha_hora': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format=FMT),
            'lugar': forms.Select(attrs={'class': 'form-select'}),
            'lugar_detalle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: al lado de la cama, ducha'}),
            'descripcion': _texto(3, 'Describa los hechos tal como pasaron, sin buscar culpables.'),
            'testigo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: lo encontró la auxiliar del turno'}),
            'accion_inmediata': _texto(2, 'Ej.: se levantó con ayuda de dos personas, se tomaron signos, se avisó al médico.'),
            'gravedad': forms.Select(attrs={'class': 'form-select'}),
            'aviso_medico': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'aviso_familia': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'aviso_familia_quien': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: hija, Marta Gómez'}),
            'golpe_cabeza': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'perdida_conciencia': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'anticoagulantes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'lesiones': _texto(2, 'Ej.: hematoma en la cadera derecha, herida pequeña en el codo.'),
            'tipo_error': forms.Select(attrs={'class': 'form-select'}),
            'prescripcion': forms.Select(attrs={'class': 'form-select'}),
            'herida': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, residente=None, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.residente = residente
        self.fields['fecha_hora'].input_formats = [FMT]
        self.fields['tipo'].choices = [('', '— Elija el tipo de evento —')] + list(self.fields['tipo'].choices)[1:]
        self.fields['gravedad'].choices = [('', '— Elija el daño —')] + list(self.fields['gravedad'].choices)[1:]
        self.fields['tipo_error'].choices = [('', '—')] + list(self.fields['tipo_error'].choices)[1:]
        from cuidados.models import Herida
        from medicamentos.models import Prescripcion
        self.fields['prescripcion'].queryset = Prescripcion.objects.filter(residente=residente).select_related('medicamento') \
            if residente else Prescripcion.objects.none()
        self.fields['prescripcion'].empty_label = '— Elija la orden médica —'
        self.fields['herida'].queryset = Herida.objects.filter(residente=residente, tipo=Herida.LPP) \
            if residente else Herida.objects.none()
        self.fields['herida'].empty_label = '— Elija la lesión —'
        if not (config and config.modo_reporte == ConfiguracionEventos.ANONIMO):
            del self.fields['anonimo']
        if not self.is_bound:
            self.initial.setdefault('fecha_hora', timezone.localtime().replace(second=0, microsecond=0))
            if residente is not None:
                self.initial.setdefault('anticoagulantes', _toma_anticoagulantes(residente))

    def clean_fecha_hora(self):
        v = self.cleaned_data['fecha_hora']
        if v > timezone.now() + timedelta(minutes=5):
            raise forms.ValidationError('La fecha no puede ser futura.')
        if v < timezone.now() - timedelta(days=30):
            raise forms.ValidationError('Solo se reportan eventos de los últimos 30 días.')
        return v

    def clean(self):
        datos = super().clean()
        tipo = datos.get('tipo')
        if tipo == MEDICACION and not datos.get('tipo_error'):
            self.add_error('tipo_error', 'Indique qué falló.')
        if tipo != CAIDA:
            for c in ('golpe_cabeza', 'perdida_conciencia', 'anticoagulantes'):
                datos[c] = False
        if tipo != MEDICACION:
            datos['tipo_error'] = ''
            datos['prescripcion'] = None
        if tipo != LPP:
            datos['herida'] = None
        if datos.get('aviso_familia') and not datos.get('aviso_familia_quien'):
            self.add_error('aviso_familia_quien', 'Indique a quién de la familia se avisó.')
        return datos


def _toma_anticoagulantes(residente):
    """Sugerencia: alguna orden activa con un anticoagulante conocido."""
    nombres = ('warfarina', 'apixaban', 'rivaroxaban', 'dabigatran', 'edoxaban', 'enoxaparina', 'heparina',
               'acenocumarol')
    from medicamentos.models import Prescripcion
    for p in Prescripcion.objects.filter(residente=residente, estado=Prescripcion.ACTIVA).select_related('medicamento'):
        if any(n in str(p.medicamento).lower() for n in nombres):
            return True
    return False


class CierreForm(forms.Form):
    causas = forms.CharField(label='Por qué pasó (causas)', widget=_texto(3, 'Ej.: piso mojado, no tenía el timbre a mano, calzado inadecuado.'))
    acciones = forms.CharField(label='Qué se va a hacer para que no se repita',
                               widget=_texto(3, 'Ej.: barras en el baño, revisión de calzado, cambio de horario de la ducha.'))
    responsable = forms.CharField(label='Responsable de las acciones', required=False,
                                  widget=forms.TextInput(attrs={'class': 'form-control'}))
    fecha_limite = forms.DateField(label='Fecha límite', required=False, input_formats=['%Y-%m-%d'],
                                   widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))


class NotaForm(forms.Form):
    texto = forms.CharField(label='Nota de seguimiento', widget=_texto(2, 'Ej.: se habló con la familia; el médico lo valoró y no requiere radiografía.'))


class VigilanciaForm(forms.ModelForm):
    class Meta:
        model = VigilanciaEvento
        fields = ['conciencia', 'dolor', 'hallazgos', 'requiere_medico']
        widgets = {
            'conciencia': forms.Select(attrs={'class': 'form-select'}),
            'dolor': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 10}),
            'hallazgos': _texto(2, 'Ej.: PA 130/80, sin hematomas nuevos, camina con andador como siempre.'),
            'requiere_medico': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['conciencia'].required = True
        self.fields['conciencia'].choices = [('', '—')] + VigilanciaEvento.CONCIENCIAS

    def clean_dolor(self):
        d = self.cleaned_data.get('dolor')
        if d is not None and d > 10:
            raise forms.ValidationError('El dolor va de 0 a 10.')
        return d


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionEventos
        fields = ['modo_reporte', 'horas_vigilancia_caida', 'intervalo_vigilancia_horas']
        widgets = {
            'modo_reporte': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'horas_vigilancia_caida': forms.NumberInput(attrs={'class': 'form-control', 'min': 12, 'max': 168}),
            'intervalo_vigilancia_horas': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 24}),
        }

    def clean(self):
        d = super().clean()
        if d.get('horas_vigilancia_caida') and d.get('intervalo_vigilancia_horas') and \
                d['intervalo_vigilancia_horas'] > d['horas_vigilancia_caida']:
            self.add_error('intervalo_vigilancia_horas', 'El intervalo no puede ser mayor que el tiempo de vigilancia.')
        return d
