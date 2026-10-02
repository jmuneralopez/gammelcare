from datetime import timedelta

from django import forms
from django.utils import timezone

from . import escalas as E

DIAS_REGISTRO_TARDIO = 30


def _fecha_widget():
    return forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d')


class _BaseValoracionForm(forms.Form):
    fecha = forms.DateField(label='Fecha de aplicación', widget=_fecha_widget())
    observaciones = forms.CharField(label='Observaciones', required=False, widget=forms.Textarea(attrs={
        'class': 'form-control', 'rows': 2,
        'placeholder': 'Condiciones de la aplicación, colaboración del residente, hallazgos.'}))

    def __init__(self, *args, escala=None, **kwargs):
        self.escala = escala
        super().__init__(*args, **kwargs)
        self.fields['fecha'].initial = timezone.localdate()

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']
        hoy = timezone.localdate()
        if fecha > hoy:
            raise forms.ValidationError('La fecha no puede ser futura.')
        if fecha < hoy - timedelta(days=DIAS_REGISTRO_TARDIO):
            raise forms.ValidationError(f'Solo se registran valoraciones de los últimos {DIAS_REGISTRO_TARDIO} días.')
        return fecha


class ItemsForm(_BaseValoracionForm):
    """Un campo de opción por ítem; el valor elegido es el índice de la opción."""

    def __init__(self, *args, escala=None, **kwargs):
        super().__init__(*args, escala=escala, **kwargs)
        for item in escala.items:
            self.fields[f'i_{item.codigo}'] = forms.TypedChoiceField(
                label=item.pregunta, coerce=int, widget=forms.RadioSelect,
                choices=[(n, f'{texto}') for n, (_p, texto) in enumerate(item.opciones)],
                error_messages={'required': 'Elija una opción.'},
            )
        if escala.cuenta_errores:
            self.fields['educacion'] = forms.ChoiceField(
                label='Nivel educativo del residente', initial='media',
                choices=[(c, t) for c, t, _a in escala.extra['educacion']],
                widget=forms.Select(attrs={'class': 'form-select'}),
            )

    def campos_items(self):
        """[(grupo, item, campo)] en orden, para la plantilla."""
        return [(i.grupo, i, self[f'i_{i.codigo}']) for i in self.escala.items]

    def respuestas(self):
        salida = {}
        for item in self.escala.items:
            n = self.cleaned_data[f'i_{item.codigo}']
            puntos, texto = item.opciones[n]
            salida[item.codigo] = {'opcion': n, 'puntos': puntos, 'texto': texto}
        return salida


class AnularForm(forms.Form):
    motivo = forms.CharField(label='Motivo de la anulación', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))


class ConfiguracionForm(forms.Form):
    def __init__(self, *args, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        for e in E.ESCALAS:
            self.fields[e.codigo] = forms.IntegerField(
                label=e.nombre, min_value=0, max_value=24, initial=config.meses(e.codigo),
                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'max-width:90px'}),
            )

    def filas(self):
        return [(e, self[e.codigo]) for e in E.ESCALAS]

    def guardar(self, usuario):
        self.config.periodicidad = {e.codigo: self.cleaned_data[e.codigo] for e in E.ESCALAS}
        self.config.actualizado_por = usuario
        self.config.save()
