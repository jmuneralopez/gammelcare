from django import forms

from .models import COMIDAS, ConfiguracionNutricion, DietaResidente, TipoDieta


def _texto(filas=2, ejemplo=''):
    return forms.Textarea(attrs={'class': 'form-control', 'rows': filas, 'placeholder': ejemplo})


class DietaForm(forms.ModelForm):
    class Meta:
        model = DietaResidente
        fields = ['tipo', 'textura', 'liquidos', 'ayuda', 'meta_liquidos_ml', 'restriccion_liquidos_ml',
                  'alimentos_evitar', 'preferencias', 'indicaciones', 'indicada_por']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'textura': forms.Select(attrs={'class': 'form-select'}),
            'liquidos': forms.Select(attrs={'class': 'form-select'}),
            'ayuda': forms.Select(attrs={'class': 'form-select'}),
            'meta_liquidos_ml': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 50}),
            'restriccion_liquidos_ml': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': 50}),
            'alimentos_evitar': _texto(2, 'Ej.: mariscos, leche entera, granos.'),
            'preferencias': _texto(2, 'Ej.: no le gusta el pescado; prefiere aguapanela caliente.'),
            'indicaciones': _texto(2),
            'indicada_por': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej.: Nutricionista Ana Ruiz'}),
        }

    def __init__(self, *args, hogar=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo'].queryset = TipoDieta.disponibles(hogar)
        self.fields['tipo'].empty_label = '— Elija la dieta —'

    def clean(self):
        datos = super().clean()
        meta, maximo = datos.get('meta_liquidos_ml'), datos.get('restriccion_liquidos_ml')
        if meta and maximo and meta > maximo:
            self.add_error('meta_liquidos_ml', 'La meta no puede ser mayor que el máximo de líquidos permitido.')
        return datos


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionNutricion
        fields = ['vaso_ml', 'meta_liquidos_ml']
        widgets = {
            'vaso_ml': forms.NumberInput(attrs={'class': 'form-control', 'min': 50, 'max': 500, 'step': 10}),
            'meta_liquidos_ml': forms.NumberInput(attrs={'class': 'form-control', 'min': 500, 'max': 4000, 'step': 50}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        activas = set(self.instance.comidas_activas or [c for c, _, _ in COMIDAS])
        horas = self.instance.horas or {}
        for codigo, nombre, hora in COMIDAS:
            self.fields[f'activa_{codigo}'] = forms.BooleanField(
                label=nombre, required=False, initial=codigo in activas,
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
            self.fields[f'hora_{codigo}'] = forms.TimeField(
                label=f'Hora de {nombre.lower()}', initial=horas.get(codigo, hora),
                widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}, format='%H:%M'))

    def filas_comidas(self):
        return [(self[f'activa_{c}'], self[f'hora_{c}']) for c, _, _ in COMIDAS]

    def clean(self):
        datos = super().clean()
        if not any(datos.get(f'activa_{c}') for c, _, _ in COMIDAS):
            raise forms.ValidationError('Marque al menos una comida.')
        return datos

    def save(self, commit=True):
        config = super().save(commit=False)
        config.comidas_activas = [c for c, _, _ in COMIDAS if self.cleaned_data.get(f'activa_{c}')]
        config.horas = {c: self.cleaned_data[f'hora_{c}'].strftime('%H:%M') for c, _, _ in COMIDAS
                        if self.cleaned_data.get(f'hora_{c}')}
        if commit:
            config.save()
        return config
