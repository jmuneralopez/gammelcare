from django import forms
from .models import NotaClinica, NotaAclaratoria


class NotaClinicaForm(forms.ModelForm):

    def __init__(self, *args, tipos_permitidos=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tipos_permitidos is not None:
            self.fields['tipo'].choices = [
                (k, v) for k, v in NotaClinica.TIPOS
                if k in tipos_permitidos
            ]
            if len(tipos_permitidos) == 1:
                self.fields['tipo'].initial = tipos_permitidos[0]

    class Meta:
        model = NotaClinica
        fields = ['tipo', 'contenido', 'diuresis', 'deposicion']
        widgets = {
            'tipo': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_tipo',
                'onchange': 'toggleEnfermeria()'
            }),
            'contenido': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Escriba el contenido de la nota clínica...'
            }),
            'diuresis': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'deposicion': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'tipo': 'Tipo de nota',
            'contenido': 'Contenido',
            'diuresis': 'Diuresis positiva',
            'deposicion': 'Deposición positiva',
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