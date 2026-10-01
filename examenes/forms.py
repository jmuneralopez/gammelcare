from django import forms
from django.conf import settings
from django.forms import formset_factory
from django.utils import timezone

from .models import AnalitoCatalogo, Examen, RevisionMedica

TIPOS_PERMITIDOS = {
    'application/pdf': (b'%PDF',),
    'image/jpeg': (b'\xff\xd8\xff',),
    'image/png': (b'\x89PNG\r\n\x1a\n',),
}
EXTENSIONES_PERMITIDAS = {'.pdf', '.jpg', '.jpeg', '.png'}


def validar_archivo_resultado(archivo):
    """Acepta solo PDF, JPG y PNG, verificando la firma real del archivo
    (no solo la extensión) y el tamaño máximo configurado."""
    import os
    extension = os.path.splitext(archivo.name)[1].lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        raise forms.ValidationError(
            f'"{archivo.name}": solo se aceptan archivos PDF, JPG o PNG.'
        )
    maximo = settings.EXAMENES_MAX_MB * 1024 * 1024
    if archivo.size > maximo:
        raise forms.ValidationError(
            f'"{archivo.name}" supera el tamaño máximo de {settings.EXAMENES_MAX_MB} MB.'
        )
    archivo.seek(0)
    cabecera = archivo.read(8)
    archivo.seek(0)
    for content_type, firmas in TIPOS_PERMITIDOS.items():
        if any(cabecera.startswith(f) for f in firmas):
            archivo.tipo_detectado = content_type
            return archivo
    raise forms.ValidationError(
        f'"{archivo.name}" no parece un PDF o una imagen válida.'
    )


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
        queryset=AnalitoCatalogo.objects.filter(activo=True), required=False,
        empty_label='— Otro (escribir nombre) —',
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
            raise forms.ValidationError('Elija un analito del catálogo o escriba el nombre.')
        if analito:
            datos['nombre'] = datos.get('nombre') or analito.nombre
            datos['unidad'] = datos.get('unidad') or analito.unidad
        rmin, rmax = datos.get('ref_min'), datos.get('ref_max')
        if rmin is not None and rmax is not None and rmin > rmax:
            raise forms.ValidationError('El mínimo de referencia es mayor que el máximo.')
        return datos


ValorFormSet = formset_factory(ValorForm, extra=0, can_delete=False)


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
        label='Motivo de la adenda',
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
