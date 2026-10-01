from django import forms
from django.conf import settings
from django.forms import formset_factory
from django.utils import timezone

from .models import AnalitoCatalogo, Examen, RevisionMedica

from gammelcare.archivos_privados import validar_archivo_clinico as validar_archivo_resultado  # noqa: E402


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Campo de varios archivos (patrón de la documentación de Django)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={
            'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png',
        }))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        limpio = super().clean
        if isinstance(data, (list, tuple)):
            archivos = [limpio(d, initial) for d in data if d]
        elif data:
            archivos = [limpio(data, initial)]
        else:
            archivos = []
        return [validar_archivo_resultado(a) for a in archivos]


def _fecha(attrs=None):
    base = {'type': 'date', 'class': 'form-control'}
    base.update(attrs or {})
    return forms.DateInput(attrs=base, format='%Y-%m-%d')


class ExamenForm(forms.ModelForm):
    class Meta:
        model = Examen
        fields = ['tipo', 'nombre', 'ordenado_por', 'entidad', 'fecha_orden', 'indicaciones']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej.: Hemograma, glucosa y creatinina',
            }),
            'ordenado_por': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej.: Dra. Gómez — medicina interna',
            }),
            'entidad': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej.: Sanitas / Laboratorio Clínico X',
            }),
            'fecha_orden': _fecha(),
            'indicaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_fecha_orden(self):
        fecha = self.cleaned_data.get('fecha_orden')
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de la orden no puede ser futura.')
        return fecha


class ValorForm(forms.Form):
    analito = forms.ModelChoiceField(
        queryset=AnalitoCatalogo.objects.none(), required=False,
        empty_label='— Otro parámetro (escribir nombre) —',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm analito-select'}),
    )
    nombre = forms.CharField(
        max_length=120, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Nombre'}),
    )
    valor = forms.DecimalField(
        max_digits=12, decimal_places=3,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': 'any'}),
    )
    unidad = forms.CharField(
        max_length=30, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
    )
    ref_min = forms.DecimalField(
        max_digits=10, decimal_places=3, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': 'any'}),
    )
    ref_max = forms.DecimalField(
        max_digits=10, decimal_places=3, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': 'any'}),
    )

    def clean(self):
        datos = super().clean()
        analito = datos.get('analito')
        if not analito and not datos.get('nombre'):
            raise forms.ValidationError('Elija un parámetro de la lista o escriba el nombre.')
        if analito:
            datos['nombre'] = datos.get('nombre') or analito.nombre
            datos['unidad'] = datos.get('unidad') or analito.unidad
        rmin, rmax = datos.get('ref_min'), datos.get('ref_max')
        if rmin is not None and rmax is not None and rmin > rmax:
            raise forms.ValidationError('El mínimo de referencia es mayor que el máximo.')
        return datos

    def __init__(self, *args, hogar=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['analito'].queryset = AnalitoCatalogo.disponibles_para(hogar)


ValorFormSet = formset_factory(ValorForm, extra=0, can_delete=False)


class AnalitoRapidoForm(forms.ModelForm):
    """Alta de un analito desde el formulario de resultados, sin salir de
    él (mismo patrón que el alta rápida de medicamentos)."""

    class Meta:
        model = AnalitoCatalogo
        fields = ['nombre', 'unidad', 'ref_min', 'ref_max']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: Ferritina'}),
            'unidad': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: ng/mL'}),
            'ref_min': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'ref_max': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
        }

    def __init__(self, *args, hogar=None, **kwargs):
        self.hogar = hogar
        super().__init__(*args, **kwargs)

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if AnalitoCatalogo.disponibles_para(self.hogar).filter(nombre__iexact=nombre).exists():
            raise forms.ValidationError('Ese parámetro ya está en la lista.')
        return nombre

    def clean(self):
        datos = super().clean()
        rmin, rmax = datos.get('ref_min'), datos.get('ref_max')
        if rmin is not None and rmax is not None and rmin > rmax:
            raise forms.ValidationError('El mínimo de referencia es mayor que el máximo.')
        return datos


class ResultadoForm(forms.Form):
    fecha_toma = forms.DateField(label='Fecha de toma o realización', widget=_fecha())
    conclusion = forms.CharField(
        label='Conclusión del informe', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    archivos = MultipleFileField(label='Archivos del resultado (PDF, JPG o PNG)', required=False)

    def clean_fecha_toma(self):
        fecha = self.cleaned_data['fecha_toma']
        if fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de toma no puede ser futura.')
        return fecha


class AdendaForm(forms.Form):
    motivo = forms.CharField(
        label='Motivo (qué llegó o qué faltaba)',
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Ej.: el laboratorio envió el reporte completo con el perfil lipídico.',
        }),
    )
    archivos = MultipleFileField(label='Archivos adicionales (PDF, JPG o PNG)', required=False)


class CorreccionValorForm(forms.Form):
    valor = forms.DecimalField(
        max_digits=12, decimal_places=3,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
    )
    unidad = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    ref_min = forms.DecimalField(
        max_digits=10, decimal_places=3, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
    )
    ref_max = forms.DecimalField(
        max_digits=10, decimal_places=3, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
    )
    motivo = forms.CharField(
        label='Motivo de la corrección',
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2, 'placeholder': 'Ej.: error de digitación, el reporte dice 1.1',
        }),
    )


class RevisionForm(forms.ModelForm):
    class Meta:
        model = RevisionMedica
        fields = ['interpretacion', 'conducta']
        widgets = {
            'interpretacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'conducta': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Ej.: sin cambios en el manejo; control de HbA1c en 3 meses.',
            }),
        }


class CancelarForm(forms.Form):
    motivo = forms.CharField(
        label='Motivo de la cancelación',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )
