from django import forms
from django.utils import timezone

from .models import ObjetivoPlan, PlanAtencion, SeguimientoObjetivo


def _fecha():
    return forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d')


def _texto(rows=3, placeholder=''):
    return forms.Textarea(attrs={'class': 'form-control', 'rows': rows, 'placeholder': placeholder})


class PlanForm(forms.ModelForm):
    class Meta:
        model = PlanAtencion
        fields = ['resumen', 'participantes', 'acuerdos_familia', 'fecha_revision']
        widgets = {
            'resumen': _texto(5, 'Diagnósticos principales, resultados de las escalas, situación funcional, cognitiva, '
                                 'nutricional y social, y lo que el residente y su familia esperan.'),
            'participantes': _texto(2, 'Ej.: Dr. Pérez (medicina), Laura (jefe de enfermería), Marta (hija), el residente.'),
            'acuerdos_familia': _texto(2, 'Ej.: la familia visitará los domingos y traerá los pañales.'),
            'fecha_revision': _fecha(),
        }

    def clean_fecha_revision(self):
        f = self.cleaned_data['fecha_revision']
        if f <= timezone.localdate():
            raise forms.ValidationError('La próxima revisión debe ser una fecha futura.')
        return f


class ObjetivoForm(forms.ModelForm):
    class Meta:
        model = ObjetivoPlan
        fields = ['area', 'necesidad', 'meta', 'intervenciones', 'responsable', 'frecuencia', 'fecha_meta', 'origen']
        widgets = {
            'area': forms.Select(attrs={'class': 'form-select'}),
            'necesidad': _texto(2, 'Ej.: riesgo alto de caídas (Tinetti 15); se cayó dos veces el último mes.'),
            'meta': _texto(2, 'Ej.: que no presente caídas en los próximos 3 meses.'),
            'intervenciones': _texto(3, 'Ej.: acompañarlo al caminar; calzado antideslizante; ejercicios de equilibrio 3 veces por semana.'),
            'responsable': forms.Select(attrs={'class': 'form-select'}),
            'frecuencia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: 3 veces por semana'}),
            'fecha_meta': _fecha(),
            'origen': forms.HiddenInput(),
        }

    def clean_fecha_meta(self):
        f = self.cleaned_data['fecha_meta']
        if f <= timezone.localdate():
            raise forms.ValidationError('La fecha para evaluarlo debe ser futura.')
        return f


class SeguimientoForm(forms.ModelForm):
    class Meta:
        model = SeguimientoObjetivo
        fields = ['estado', 'nota']
        widgets = {
            'estado': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'nota': _texto(2, 'Qué se hizo y cómo respondió el residente.'),
        }
