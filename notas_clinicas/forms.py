from django import forms
from .models import NotaClinica, NotaAclaratoria


class NotaClinicaForm(forms.ModelForm):
    class Meta:
        model = NotaClinica
        fields = ['tipo', 'contenido']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'contenido': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Escriba el contenido de la nota clínica...'
            })
        }
        labels = {
            'tipo': 'Tipo de nota',
            'contenido': 'Contenido'
        }


class NotaAclaratoriaForm(forms.ModelForm):
    class Meta:
        model = NotaAclaratoria
        fields = ['contenido']
        widgets = {
            'contenido': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Escriba la aclaración sobre la nota original...'
            })
        }
        labels = {
            'contenido': 'Contenido de la aclaración'
        }