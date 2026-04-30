from django import forms
from .models import Residente, AsignacionCama
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
        empty_label='Seleccione una cama disponible'
    )

    def __init__(self, *args, hogar=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hogar:
            self.fields['cama'].queryset = Cama.objects.filter(
                habitacion__departamento__hogar=hogar,
                estado='disponible',
                activo=True
            )