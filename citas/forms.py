from datetime import timedelta

from django import forms
from django.utils import timezone

from gammelcare.archivos_privados import validar_archivo_clinico

from .models import Cita

FORMATO_FECHA_HORA = '%Y-%m-%dT%H:%M'


def _fecha_hora():
    return forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format=FORMATO_FECHA_HORA)


# Las EPS dan citas de especialista con meses de espera; un control anual
# también se agenda con un año de anticipación. Más allá de eso casi
# siempre es un error de digitación del año.
MAX_DIAS_ANTICIPACION = 400


def _validar_fecha(valor, margen_horas=1):
    # Una hora de margen: se agenda mientras se habla por teléfono con la EPS.
    if valor and valor < timezone.now() - timedelta(hours=margen_horas):
        raise forms.ValidationError('Esa fecha ya pasó.')
    if valor and valor > timezone.now() + timedelta(days=MAX_DIAS_ANTICIPACION):
        raise forms.ValidationError('La fecha está a más de un año. Revise el año que escribió.')
    return valor


_no_pasada = _validar_fecha


class CitaForm(forms.ModelForm):
    class Meta:
        model = Cita
        fields = ['tipo', 'especialidad', 'profesional', 'lugar', 'fecha_hora', 'requiere_ayuno',
                  'preparacion', 'acompanante', 'transporte', 'observaciones']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'especialidad': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: Cardiología'}),
            'profesional': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: Dr. Ramírez'}),
            'lugar': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej.: Clínica del Country, Cra 16 # 82-57, consultorio 304',
            }),
            'fecha_hora': _fecha_hora(),
            'requiere_ayuno': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'preparacion': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Ej.: ayuno de 8 horas; llevar exámenes anteriores y lista de medicamentos.',
            }),
            'acompanante': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: hija (Marta) o auxiliar del turno'}),
            'transporte': forms.Select(attrs={'class': 'form-select'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_hora'].input_formats = [FORMATO_FECHA_HORA]

    def clean_fecha_hora(self):
        return _no_pasada(self.cleaned_data.get('fecha_hora'))


class CerrarForm(forms.Form):
    estado = forms.ChoiceField(
        label='¿Qué pasó?', choices=[(Cita.CUMPLIDA, 'Se cumplió'), (Cita.NO_ASISTIO, 'No asistió')],
        widget=forms.RadioSelect,
    )
    resumen = forms.CharField(
        label='Resumen', widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 4,
            'placeholder': 'Diagnóstico o concepto, cambios en medicamentos, exámenes ordenados, próximo control. '
                           'Si no asistió: por qué.',
        }),
    )
    archivo = forms.FileField(
        label='Soporte (fórmula, orden o resumen de la atención) — PDF, JPG o PNG', required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'}),
    )

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        return validar_archivo_clinico(archivo) if archivo else None


class CancelarForm(forms.Form):
    motivo = forms.CharField(label='Motivo de la cancelación', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))


class ReprogramarForm(forms.Form):
    fecha_hora = forms.DateTimeField(label='Nueva fecha y hora', widget=_fecha_hora(), input_formats=[FORMATO_FECHA_HORA])
    lugar = forms.CharField(label='Nuevo lugar (déjelo vacío si no cambia)', required=False, max_length=200,
                            widget=forms.TextInput(attrs={'class': 'form-control'}))
    motivo = forms.CharField(label='Motivo', widget=forms.Textarea(attrs={
        'class': 'form-control', 'rows': 2, 'placeholder': 'Ej.: la EPS movió la cita; el residente amaneció con fiebre.',
    }))

    def clean_fecha_hora(self):
        return _validar_fecha(self.cleaned_data.get('fecha_hora'), margen_horas=0)
