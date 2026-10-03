from datetime import timedelta

from django import forms
from django.utils import timezone

from gammelcare.archivos_privados import validar_archivo_clinico

from .models import DETALLES, TIPOS_CUIDADO, Herida, PlanCuidados, SeguimientoHerida

FMT = '%Y-%m-%dT%H:%M'
HORAS_REGISTRO_TARDIO = 24


def _fecha_hora():
    return forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format=FMT)


def _texto(filas=2, ejemplo=''):
    return forms.Textarea(attrs={'class': 'form-control', 'rows': filas, 'placeholder': ejemplo})


def _num(attrs=None):
    base = {'class': 'form-control', 'inputmode': 'decimal'}
    base.update(attrs or {})
    return forms.NumberInput(attrs=base)


def validar_hora_pasada(valor, horas=HORAS_REGISTRO_TARDIO):
    ahora = timezone.now()
    if valor > ahora + timedelta(minutes=5):
        raise forms.ValidationError('La hora no puede ser futura.')
    if valor < ahora - timedelta(hours=horas):
        raise forms.ValidationError(f'Solo se registran cuidados de las últimas {horas} horas.')
    return valor


class CuidadoForm(forms.Form):
    """Registro de un cuidado con hora y observación (la planilla usa la hora actual)."""
    tipo = forms.ChoiceField(label='Cuidado', choices=TIPOS_CUIDADO, widget=forms.Select(attrs={'class': 'form-select'}))
    detalle = forms.CharField(label='Cómo', widget=forms.Select(attrs={'class': 'form-select'}))
    fecha_hora = forms.DateTimeField(label='Hora en que se hizo', input_formats=[FMT], widget=_fecha_hora())
    observaciones = forms.CharField(label='Observación', required=False,
                                    widget=_texto(2, 'Ej.: piel enrojecida en el talón derecho; se informó a la jefe.'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault('fecha_hora', timezone.localtime().replace(second=0, microsecond=0))

    def clean_fecha_hora(self):
        return validar_hora_pasada(self.cleaned_data['fecha_hora'])

    def clean(self):
        datos = super().clean()
        tipo, detalle = datos.get('tipo'), datos.get('detalle')
        if tipo and detalle not in dict(DETALLES.get(tipo, [])):
            self.add_error('detalle', 'Elija una opción de la lista.')
        return datos


class PlanCuidadosForm(forms.ModelForm):
    class Meta:
        model = PlanCuidados
        fields = ['cambios_posicion', 'intervalo_posicion_horas', 'usa_panal', 'banio', 'higiene_oral',
                  'movilizacion', 'indicaciones']
        widgets = {
            'cambios_posicion': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'intervalo_posicion_horas': forms.Select(attrs={'class': 'form-select'}),
            'usa_panal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'banio': forms.Select(attrs={'class': 'form-select'}),
            'higiene_oral': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'movilizacion': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'indicaciones': _texto(3, 'Ej.: colchón antiescaras; proteger talones con almohada; baño con dos personas.'),
        }


class HeridaForm(forms.ModelForm):
    class Meta:
        model = Herida
        fields = ['tipo', 'ubicacion', 'ubicacion_detalle', 'estadio_inicial', 'origen', 'fecha_deteccion',
                  'descripcion']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'ubicacion': forms.Select(attrs={'class': 'form-select'}),
            'ubicacion_detalle': forms.TextInput(attrs={'class': 'form-control',
                                                        'placeholder': 'Ej.: borde externo, 3 cm arriba del tobillo'}),
            'estadio_inicial': forms.Select(attrs={'class': 'form-select'}),
            'origen': forms.Select(attrs={'class': 'form-select'}),
            'fecha_deteccion': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'descripcion': _texto(3, 'Cómo se encontró, a qué se atribuye y qué se hizo.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estadio_inicial'].choices = [('', '— Solo para lesiones por presión —')] + Herida.ESTADIOS
        self.fields['fecha_deteccion'].input_formats = ['%Y-%m-%d']

    def clean_fecha_deteccion(self):
        f = self.cleaned_data['fecha_deteccion']
        if f > timezone.localdate():
            raise forms.ValidationError('La fecha no puede ser futura.')
        return f

    def clean(self):
        datos = super().clean()
        if datos.get('tipo') == Herida.LPP and not datos.get('estadio_inicial'):
            self.add_error('estadio_inicial', 'Indique el estadio de la lesión por presión.')
        if datos.get('tipo') != Herida.LPP:
            datos['estadio_inicial'] = ''
        if datos.get('ubicacion') == 'otra' and not datos.get('ubicacion_detalle'):
            self.add_error('ubicacion_detalle', 'Describa dónde está la herida.')
        return datos


class SeguimientoForm(forms.ModelForm):
    foto_archivo = forms.FileField(label='Foto de la herida', required=False,
                                   widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*',
                                                                         'capture': 'environment'}))

    class Meta:
        model = SeguimientoHerida
        fields = ['fecha_hora', 'largo_cm', 'ancho_cm', 'profundidad_cm', 'estadio', 'lecho', 'exudado',
                  'piel_alrededor', 'signos_infeccion', 'dolor', 'curacion', 'proxima_curacion', 'observaciones']
        widgets = {
            'fecha_hora': _fecha_hora(),
            'largo_cm': _num({'step': '0.1', 'min': 0}), 'ancho_cm': _num({'step': '0.1', 'min': 0}),
            'profundidad_cm': _num({'step': '0.1', 'min': 0}),
            'estadio': forms.Select(attrs={'class': 'form-select'}),
            'lecho': forms.Select(attrs={'class': 'form-select'}),
            'exudado': forms.Select(attrs={'class': 'form-select'}),
            'piel_alrededor': forms.Select(attrs={'class': 'form-select'}),
            'signos_infeccion': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dolor': _num({'min': 0, 'max': 10}),
            'curacion': _texto(3, 'Ej.: lavado con solución salina, hidrocoloide, apósito de espuma.'),
            'proxima_curacion': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'observaciones': _texto(2),
        }

    def __init__(self, *args, herida=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.herida = herida
        self.fields['fecha_hora'].input_formats = [FMT]
        self.fields['proxima_curacion'].input_formats = ['%Y-%m-%d']
        self.fields['lecho'].choices = [('', '—')] + SeguimientoHerida.LECHOS
        if herida is not None and herida.es_lpp:
            self.fields['estadio'].choices = [('', '— Igual que antes —')] + Herida.ESTADIOS
        else:
            del self.fields['estadio']
        if not self.is_bound:
            self.initial.setdefault('fecha_hora', timezone.localtime().replace(second=0, microsecond=0))

    def clean_fecha_hora(self):
        return validar_hora_pasada(self.cleaned_data['fecha_hora'], horas=72)

    def clean_dolor(self):
        d = self.cleaned_data.get('dolor')
        if d is not None and d > 10:
            raise forms.ValidationError('El dolor va de 0 a 10.')
        return d

    def clean_foto_archivo(self):
        f = self.cleaned_data.get('foto_archivo')
        if f:
            validar_archivo_clinico(f)
            if f.tipo_detectado == 'application/pdf':
                raise forms.ValidationError('Suba una foto (JPG o PNG).')
        return f

    def clean(self):
        datos = super().clean()
        campos = ['largo_cm', 'ancho_cm', 'lecho', 'curacion', 'observaciones']
        if not any(datos.get(c) for c in campos) and not datos.get('foto_archivo'):
            raise forms.ValidationError('Registre al menos las medidas, el aspecto, la curación, una observación o una foto.')
        return datos


class CerrarHeridaForm(forms.Form):
    motivo = forms.ChoiceField(label='Motivo', choices=Herida.MOTIVOS_CIERRE,
                               widget=forms.Select(attrs={'class': 'form-select'}))
    nota = forms.CharField(label='Nota', required=False, widget=_texto(2, 'Ej.: cicatrizada, piel íntegra.'))

    def clean(self):
        datos = super().clean()
        if datos.get('motivo') == 'error' and not datos.get('nota'):
            self.add_error('nota', 'Explique el error.')
        return datos


class AnularForm(forms.Form):
    motivo = forms.CharField(label='Motivo de la anulación', widget=_texto(2, 'Ej.: se registró en el residente equivocado.'))
