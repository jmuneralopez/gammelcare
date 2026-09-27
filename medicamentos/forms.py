from django import forms
from django.forms import formset_factory

from .models import (
    Medicamento, Prescripcion, IngresoMedicamento, Administracion,
    UNIDADES_DOSIS, VIA_ADMINISTRACION,
)

DIAS_SEMANA_CHOICES = [
    ('L', 'Lun'), ('M', 'Mar'), ('X', 'Mié'),
    ('J', 'Jue'), ('V', 'Vie'), ('S', 'Sáb'), ('D', 'Dom'),
]

DURACION_INDEFINIDA = 'indefinida'
DURACION_DIAS = 'dias'
DURACION_FECHA = 'fecha'
DURACION_CHOICES = [
    (DURACION_INDEFINIDA, 'Indefinida'),
    (DURACION_DIAS, 'Número de días'),
    (DURACION_FECHA, 'Hasta una fecha'),
]


class MedicamentoRapidoForm(forms.ModelForm):
    """Alta rápida de un medicamento desde el modal — sin salir del
    formulario donde se está usando (ver plan 2.1)."""

    class Meta:
        model = Medicamento
        fields = [
            'nombre_generico', 'nombre_comercial', 'concentracion',
            'forma_farmaceutica', 'unidad_dosificacion',
            'requiere_refrigeracion', 'control_especial',
        ]
        widgets = {
            'nombre_generico': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej: Acetaminofén'
            }),
            'nombre_comercial': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej: Dolex (opcional)'
            }),
            'concentracion': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej: 500 mg'
            }),
            'forma_farmaceutica': forms.Select(attrs={'class': 'form-select'}),
            'unidad_dosificacion': forms.Select(attrs={'class': 'form-select'}),
            'requiere_refrigeracion': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'control_especial': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'requiere_refrigeracion': 'Requiere refrigeración',
            'control_especial': 'Medicamento de control especial',
        }


class PrescripcionForm(forms.ModelForm):
    medicamento = forms.ModelChoiceField(
        queryset=Medicamento.objects.filter(activo=True),
        widget=forms.Select(attrs={
            'class': 'form-select select2-medicamento',
            'data-url': '/medicamentos/buscar/'
        }),
        label='Medicamento',
        empty_label='Buscar medicamento...'
    )
    duracion_tipo = forms.ChoiceField(
        choices=DURACION_CHOICES,
        initial=DURACION_INDEFINIDA,
        widget=forms.RadioSelect,
        label='Duración'
    )
    duracion_dias = forms.IntegerField(
        required=False, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Nº de días'})
    )
    duracion_fecha = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    dias_semana_sel = forms.MultipleChoiceField(
        choices=DIAS_SEMANA_CHOICES,
        initial=[c[0] for c in DIAS_SEMANA_CHOICES],
        widget=forms.CheckboxSelectMultiple,
        label='Días de la semana'
    )
    # Horas de la pauta, en CSV "07:00,20:00" — lo arma el JS con los
    # botones de pauta (ver plan 2.2) y siempre se puede editar a mano.
    horas = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label='Horarios'
    )

    class Meta:
        model = Prescripcion
        fields = [
            'medicamento', 'dosis_cantidad', 'dosis_unidad', 'via_administracion',
            'tipo_pauta', 'frecuencia_minima_horas', 'dosis_maxima_dia',
            'fecha_inicio', 'cantidad_total_formulada', 'indicaciones',
            'diagnostico', 'formulada_por', 'fecha_formula', 'numero_formula',
            'archivo_formula',
        ]
        widgets = {
            'dosis_cantidad': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'dosis_unidad': forms.Select(attrs={'class': 'form-select'}),
            'via_administracion': forms.Select(attrs={'class': 'form-select'}),
            'tipo_pauta': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_pauta'}),
            'frecuencia_minima_horas': forms.NumberInput(attrs={'class': 'form-control'}),
            'dosis_maxima_dia': forms.NumberInput(attrs={'class': 'form-control'}),
            'fecha_inicio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'cantidad_total_formulada': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'indicaciones': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Ej: con alimentos, no triturar, media hora antes'
            }),
            'diagnostico': forms.Select(attrs={'class': 'form-select'}),
            'formulada_por': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej: Dr. Restrepo — Sanitas'
            }),
            'fecha_formula': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'numero_formula': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'formulada_por': 'Formulada por',
            'fecha_formula': 'Fecha de la fórmula',
            'numero_formula': 'Número de fórmula',
            'archivo_formula': 'Archivo de la fórmula (foto o escaneo)',
        }

    def __init__(self, *args, residente=None, **kwargs):
        super().__init__(*args, **kwargs)
        if residente is not None:
            self.fields['diagnostico'].queryset = residente.diagnosticos.filter(activo=True)
        self.fields['diagnostico'].required = False
        self.fields['diagnostico'].empty_label = 'Sin diagnóstico asociado'

    def clean(self):
        cleaned = super().clean()
        tipo_pauta = cleaned.get('tipo_pauta')
        horas = cleaned.get('horas', '')
        duracion_tipo = cleaned.get('duracion_tipo')

        if tipo_pauta == Prescripcion.HORARIOS_FIJOS and not horas.strip():
            self.add_error('horas', 'Defina al menos un horario para esta pauta.')

        if duracion_tipo == DURACION_DIAS and not cleaned.get('duracion_dias'):
            self.add_error('duracion_dias', 'Indique el número de días.')
        if duracion_tipo == DURACION_FECHA and not cleaned.get('duracion_fecha'):
            self.add_error('duracion_fecha', 'Indique la fecha de fin.')

        return cleaned

    def horas_lista(self):
        crudo = self.cleaned_data.get('horas', '')
        return [h.strip() for h in crudo.split(',') if h.strip()]

    def dias_semana_str(self):
        seleccion = self.cleaned_data.get('dias_semana_sel') or []
        return ''.join(c for c, _ in DIAS_SEMANA_CHOICES if c in seleccion)


class SuspensionForm(forms.Form):
    motivo_suspension = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': 'Quién ordenó suspender el tratamiento y por qué'
        }),
        label='Motivo de suspensión'
    )


# ── Ingreso de medicamentos — formulario multi-fila ─────────────
# Mismo patrón de formset dinámico ya construido para diagnósticos CIE-10
# en residente_form.html (ver plan 3.4).

class IngresoEncabezadoForm(forms.Form):
    entregado_por = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre de quien entrega (familiar)'
        }),
        label='Entregado por'
    )
    fecha_ingreso = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Fecha de ingreso'
    )
    observaciones = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        label='Observaciones'
    )


class IngresoFilaForm(forms.Form):
    """Fila del formset — opcional a nivel de formulario para permitir
    filas vacías que se descartan al guardar."""
    medicamento = forms.ModelChoiceField(
        queryset=Medicamento.objects.filter(activo=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select select2-medicamento-inline',
            'data-url': '/medicamentos/buscar/'
        }),
        label='Medicamento',
        empty_label='Buscar medicamento...'
    )
    lote = forms.CharField(
        max_length=50, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lote'})
    )
    cantidad_ingresada = forms.DecimalField(
        max_digits=8, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Cantidad'})
    )
    unidad = forms.ChoiceField(
        choices=IngresoMedicamento.UNIDADES_INGRESO,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    fecha_vencimiento = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )

    def fila_completa(self):
        """True si la fila trae lo mínimo para crear un ingreso — se usa
        para descartar filas en blanco del formset sin marcarlas como
        error de validación."""
        return bool(
            self.cleaned_data.get('medicamento') and
            self.cleaned_data.get('lote') and
            self.cleaned_data.get('cantidad_ingresada') and
            self.cleaned_data.get('fecha_vencimiento')
        )

    def clean(self):
        cleaned = super().clean()
        algo_diligenciado = any(cleaned.get(campo) for campo in
                                 ['medicamento', 'lote', 'cantidad_ingresada', 'fecha_vencimiento'])
        if algo_diligenciado and not self.fila_completa():
            raise forms.ValidationError(
                'Complete medicamento, lote, cantidad y vencimiento en esta fila, o déjela vacía.'
            )
        return cleaned


IngresoFormSet = formset_factory(IngresoFilaForm, extra=1)


# ── Registro de administración / no administración ──────────────

class AdministrarForm(forms.Form):
    cantidad_administrada = forms.DecimalField(max_digits=6, decimal_places=2)
    observacion = forms.CharField(required=False, widget=forms.Textarea)


class NoAdministrarForm(forms.Form):
    motivo_no_administracion = forms.ChoiceField(choices=Administracion.MOTIVOS_NO_ADMINISTRACION)
    observacion = forms.CharField(required=False, widget=forms.Textarea)


class UsoBotiquinForm(forms.Form):
    motivo_uso_botiquin = forms.ChoiceField(choices=Administracion.MOTIVOS_USO_BOTIQUIN)
    observacion = forms.CharField(widget=forms.Textarea)


class AnulacionForm(forms.Form):
    motivo_anulacion = forms.CharField(widget=forms.Textarea)
