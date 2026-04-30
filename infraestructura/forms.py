from django import forms
from .models import Departamento, Habitacion, Cama


class DepartamentoForm(forms.ModelForm):
    class Meta:
        model = Departamento
        fields = ['nombre', 'descripcion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre del departamento'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción opcional'
            }),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        labels = {
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'activo': 'Activo'
        }


class HabitacionForm(forms.ModelForm):
    class Meta:
        model = Habitacion
        fields = ['departamento', 'numero', 'descripcion', 'activo']
        widgets = {
            'departamento': forms.Select(attrs={'class': 'form-select'}),
            'numero': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número o código de habitación'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción opcional'
            }),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        labels = {
            'departamento': 'Departamento',
            'numero': 'Número',
            'descripcion': 'Descripción',
            'activo': 'Activo'
        }


class CamaForm(forms.ModelForm):
    class Meta:
        model = Cama
        fields = ['habitacion', 'codigo', 'estado', 'activo']
        widgets = {
            'habitacion': forms.Select(attrs={'class': 'form-select'}),
            'codigo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Código de la cama'
            }),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        labels = {
            'habitacion': 'Habitación',
            'codigo': 'Código',
            'estado': 'Estado',
            'activo': 'Activo'
        }