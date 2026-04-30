from django import forms
from django.db import models
from .models import Residente, ExpedienteIngreso, ExamenIngreso, DiagnosticoResidente
from catalogos.models import CodigoCIE10, EPS, ServicioAmbulancia
from infraestructura.models import Cama


class ResidenteForm(forms.Form):
    nombre_completo = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre completo del residente'
        }),
        label='Nombre completo'
    )
    tipo_documento = forms.ChoiceField(
        choices=Residente.TIPO_DOCUMENTO,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tipo de documento'
    )
    numero_documento = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Número de documento'
        }),
        label='Número de documento'
    )
    fecha_nacimiento = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d'],
        label='Fecha de nacimiento'
    )
    nacionalidad = forms.CharField(
        max_length=100,
        initial='Colombiana',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nacionalidad'
        }),
        label='Nacionalidad'
    )
    eps = forms.ModelChoiceField(
        queryset=EPS.objects.filter(activo=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select select2-eps',
            'data-url': '/catalogos/buscar/eps/'
        }),
        label='EPS',
        empty_label='Buscar EPS...'
    )
    servicio_ambulancia = forms.ModelChoiceField(
        queryset=ServicioAmbulancia.objects.filter(activo=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select select2-ambulancia',
            'data-url': '/catalogos/buscar/ambulancia/'
        }),
        label='Servicio de ambulancia',
        empty_label='Buscar servicio...'
    )
    contacto_emergencia = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre y teléfono del contacto'
        }),
        label='Contacto de emergencia'
    )
    cama = forms.ModelChoiceField(
        queryset=Cama.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Cama a asignar',
        required=False,
        empty_label='Sin cambio de cama (mantener actual)'
    )

    def __init__(self, *args, hogar=None, cama_actual=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hogar:
            from django.db.models import Q
            camas = Cama.objects.filter(
                habitacion__departamento__hogar=hogar,
                activo=True
            ).filter(
                Q(estado='disponible') |
                Q(pk=cama_actual.pk if cama_actual else None)
            )
            self.fields['cama'].queryset = camas


class ExpedienteIngresoForm(forms.ModelForm):
    class Meta:
        model = ExpedienteIngreso
        fields = ['alergias', 'inventario_ingreso', 'observaciones']
        widgets = {
            'alergias': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Alergias conocidas'
            }),
            'inventario_ingreso': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 5,
                'placeholder': 'Liste las pertenencias del residente'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Observaciones generales'
            }),
        }
        labels = {
            'alergias': 'Alergias',
            'inventario_ingreso': 'Inventario de Ingreso',
            'observaciones': 'Observaciones generales',
        }


class ExamenIngresoForm(forms.ModelForm):
    class Meta:
        model = ExamenIngreso
        fields = [
            'peso', 'talla', 'presion_arterial',
            'frecuencia_cardiaca', 'temperatura', 'saturacion_oxigeno',
            'procedencia', 'estado_mental', 'movilidad', 'condicion_nutricional',
            'observaciones_fisicas', 'antecedentes_medicos', 'antecedentes_familiares',
        ]
        widgets = {
            'peso': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'kg', 'step': '0.01'
            }),
            'talla': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'cm', 'step': '0.01'
            }),
            'presion_arterial': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'ej: 120/80'
            }),
            'frecuencia_cardiaca': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'lpm'
            }),
            'temperatura': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '°C', 'step': '0.1'
            }),
            'saturacion_oxigeno': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '%', 'step': '0.1'
            }),
            'procedencia': forms.Select(attrs={'class': 'form-select'}),
            'estado_mental': forms.Select(attrs={'class': 'form-select'}),
            'movilidad': forms.Select(attrs={'class': 'form-select'}),
            'condicion_nutricional': forms.Select(attrs={'class': 'form-select'}),
            'observaciones_fisicas': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Golpes, cortes, heridas, amputaciones...'
            }),
            'antecedentes_medicos': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Enfermedades previas, cirugías...'
            }),
            'antecedentes_familiares': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Enfermedades hereditarias...'
            }),
        }


class DiagnosticoForm(forms.ModelForm):
    codigo_cie10 = forms.ModelChoiceField(
        queryset=CodigoCIE10.objects.all(),
        widget=forms.Select(attrs={
            'class': 'form-select select2-cie10',
            'data-url': '/catalogos/buscar/cie10/'
        }),
        label='Código CIE-10',
        empty_label='Buscar código o descripción...'
    )

    class Meta:
        model = DiagnosticoResidente
        fields = ['codigo_cie10', 'observacion']
        widgets = {
            'observacion': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Observación sobre este diagnóstico'
            })
        }
        labels = {
            'observacion': 'Observación'
        }