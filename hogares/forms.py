from django import forms
from .models import Hogar


class HogarForm(forms.ModelForm):
    class Meta:
        model = Hogar
        fields = ['nombre', 'nit', 'direccion', 'telefono', 'correo', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre del hogar geriátrico'
            }),
            'nit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'NIT de la organización'
            }),
            'direccion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Dirección física'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Teléfono de contacto'
            }),
            'correo': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Correo electrónico'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'nombre': 'Nombre',
            'nit': 'NIT',
            'direccion': 'Dirección',
            'telefono': 'Teléfono',
            'correo': 'Correo electrónico',
            'activo': 'Hogar activo',
        }