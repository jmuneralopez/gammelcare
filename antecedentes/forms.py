from django import forms

from catalogos.models import CodigoCIE10

from .models import Alergia, Antecedente


class SelectSoloSeleccionado(forms.Select):
    """Select para catálogos grandes que se buscan por AJAX (Select2): solo
    imprime la opción elegida, no las 14.000 del CIE-10."""

    def optgroups(self, name, value, attrs=None):
        elegidos = {str(v) for v in value if v not in (None, '')}
        grupos = super().optgroups(name, value, attrs)
        return [
            (g, [o for o in opciones if str(o['value']) in elegidos or o['value'] == ''], i)
            for g, opciones, i in grupos
        ]


class AlergiaForm(forms.ModelForm):
    class Meta:
        model = Alergia
        fields = ['tipo', 'medicamento', 'sustancia', 'reaccion', 'descripcion_reaccion', 'severidad', 'fuente']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'medicamento': SelectSoloSeleccionado(attrs={'class': 'form-select select2-ajax', 'data-url': '/medicamentos/buscar/', 'data-placeholder': 'Buscar medicamento (opcional)'}),
            'sustancia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: Penicilina, Mariscos, Látex'}),
            'reaccion': forms.Select(attrs={'class': 'form-select'}),
            'descripcion_reaccion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'severidad': forms.Select(attrs={'class': 'form-select'}),
            'fuente': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, hogar=None, **kwargs):
        super().__init__(*args, **kwargs)
        from medicamentos.models import Medicamento
        from django.db.models import Q
        self.fields['medicamento'].required = False
        self.fields['medicamento'].queryset = Medicamento.objects.filter(activo=True).filter(
            Q(hogar__isnull=True) | Q(hogar=hogar)
        ).order_by('nombre_generico')
        self.fields['medicamento'].empty_label = '— No está en el catálogo / no aplica —'
        self.fields['sustancia'].required = False

    def clean(self):
        datos = super().clean()
        medicamento = datos.get('medicamento')
        if medicamento:
            datos['tipo'] = Alergia.MEDICAMENTO
            if not datos.get('sustancia'):
                datos['sustancia'] = medicamento.nombre_generico
        if not datos.get('sustancia'):
            self.add_error('sustancia', 'Escriba a qué es alérgico o elija el medicamento del catálogo.')
        return datos


class AntecedenteForm(forms.ModelForm):
    codigo_cie10 = forms.ModelChoiceField(
        queryset=CodigoCIE10.objects.all(), required=False, label='Código CIE-10 (opcional)',
        widget=SelectSoloSeleccionado(attrs={'class': 'form-select select2-ajax', 'data-url': '/catalogos/buscar/cie10/', 'data-placeholder': 'Buscar código o enfermedad (opcional)'}),
    )

    class Meta:
        model = Antecedente
        fields = ['tipo', 'descripcion', 'codigo_cie10', 'cuando', 'observaciones']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'descripcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: Hipertensión arterial, Reemplazo de cadera'}),
            'cuando': forms.TextInput(attrs={'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class InactivarForm(forms.Form):
    motivo = forms.CharField(
        label='Motivo', widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Ej.: registrada por error en otro residente; descartada por el alergólogo.',
        }),
    )
