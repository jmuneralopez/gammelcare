import re

from django import forms

from .models import ConfiguracionMedicamentos


class DevolucionForm(forms.Form):
    lotes = forms.MultipleChoiceField(label='Lotes que se devuelven', widget=forms.CheckboxSelectMultiple,
                                      error_messages={'required': 'Elija al menos un lote.'})
    entregado_a = forms.CharField(label='Se entrega a (nombre y parentesco)', max_length=150,
                                  widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: Marta Gómez (hija)'}))
    motivo = forms.CharField(label='Motivo', required=False, max_length=300,
                             widget=forms.TextInput(attrs={'class': 'form-control',
                                                           'placeholder': 'Ej.: egreso del residente; orden suspendida'}))

    def __init__(self, *args, lotes=(), **kwargs):
        super().__init__(*args, **kwargs)
        self._lotes = {str(l.pk): l for l in lotes}
        self.fields['lotes'].choices = [(str(l.pk), str(l.pk)) for l in lotes]

    def clean_lotes(self):
        return [self._lotes[pk] for pk in self.cleaned_data['lotes'] if pk in self._lotes]


HORAS = [('desayuno', 'Desayuno'), ('almuerzo', 'Almuerzo'), ('cena', 'Cena'), ('noche', 'Noche')]


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionMedicamentos
        fields = ['dias_semaforo_verde', 'dias_semaforo_amarillo', 'ventana_ronda_horas', 'minutos_anulacion']
        widgets = {f: forms.NumberInput(attrs={'class': 'form-control', 'style': 'max-width:140px'})
                   for f in ['dias_semaforo_verde', 'dias_semaforo_amarillo', 'ventana_ronda_horas', 'minutos_anulacion']}
        labels = {
            'dias_semaforo_verde': 'Verde: vence en más de (días)',
            'dias_semaforo_amarillo': 'Rojo: vence en menos de (días)',
            'ventana_ronda_horas': 'La ronda marca "ahora" una franja dentro de (horas)',
            'minutos_anulacion': 'Quien registró un suministro puede anularlo durante (minutos)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        horas = self.instance.horas_estandar or {}
        for clave, etiqueta in HORAS:
            self.fields[f'hora_{clave}'] = forms.CharField(
                label=f'Hora estándar: {etiqueta}', initial=horas.get(clave, ''), required=False,
                widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control', 'style': 'max-width:140px'}))

    def clean(self):
        datos = super().clean()
        verde, amarillo = datos.get('dias_semaforo_verde'), datos.get('dias_semaforo_amarillo')
        if verde is not None and amarillo is not None and amarillo >= verde:
            self.add_error('dias_semaforo_amarillo', 'Debe ser menor que el límite del verde.')
        for clave, _ in HORAS:
            v = datos.get(f'hora_{clave}') or ''
            if v and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', v[:5]):
                self.add_error(f'hora_{clave}', 'Hora no válida.')
        if datos.get('ventana_ronda_horas') is not None and not 1 <= datos['ventana_ronda_horas'] <= 12:
            self.add_error('ventana_ronda_horas', 'Entre 1 y 12 horas.')
        if datos.get('minutos_anulacion') is not None and not 5 <= datos['minutos_anulacion'] <= 1440:
            self.add_error('minutos_anulacion', 'Entre 5 y 1440 minutos.')
        return datos

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.horas_estandar = {c: (self.cleaned_data.get(f'hora_{c}') or '')[:5] for c, _ in HORAS
                              if self.cleaned_data.get(f'hora_{c}')}
        if commit:
            obj.save()
        return obj

    def campos_horas(self):
        return [self[f'hora_{c}'] for c, _ in HORAS]
