from django.db import models
from django import forms
from .models import Residente, ExpedienteIngreso
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
        }),
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
    eps = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'EPS del residente'
        }),
        label='EPS'
    )
    servicio_ambulancia = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Servicio de ambulancia'
        }),
        label='Servicio de ambulancia'
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
            # Camas disponibles + la cama actual si existe
            camas = Cama.objects.filter(
                habitacion__departamento__hogar=hogar,
                activo=True
            ).filter(
                models.Q(estado='disponible') |
                models.Q(pk=cama_actual.pk if cama_actual else None)
            )
            self.fields['cama'].queryset = camas


class ExpedienteIngresoForm(forms.ModelForm):
    class Meta:
        model = ExpedienteIngreso
        fields = [
            'diagnosticos',
            'examen_ingreso',
            'alergias',
            'observaciones',
            'inventario_ingreso'
        ]
        widgets = {
            'diagnosticos': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Diagnósticos del residente al ingreso'
            }),
            'examen_ingreso': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 5,
                'placeholder': 'Resultados del examen físico de ingreso'
            }),
            'alergias': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Alergias conocidas (medicamentos, alimentos, etc.)'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Observaciones generales'
            }),
            'inventario_ingreso': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 5,
                'placeholder': 'Liste las pertenencias del residente al momento del ingreso'
            }),
        }
        labels = {
            'diagnosticos': 'Diagnósticos',
            'examen_ingreso': 'Examen de Ingreso',
            'alergias': 'Alergias',
            'observaciones': 'Observaciones',
            'inventario_ingreso': 'Inventario de Ingreso',
        }