from django import forms

from residentes.models import Residente
from usuarios.models import Rol

from .models import Alerta
from .reglas import REGLAS, UMBRALES

ROLES_ELEGIBLES = [(c, n) for c, n in Rol.ROLES if c != Rol.SUPERADMIN]
VIGENCIAS = [(8, 'Un turno (8 horas)'), (24, 'Un día'), (72, 'Tres días'), (168, 'Una semana')]


class AvisoForm(forms.Form):
    titulo = forms.CharField(label='Aviso', max_length=200, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Ej.: Ofrecer líquidos cada 2 horas a la señora Rosa',
    }))
    mensaje = forms.CharField(label='Detalle (opcional)', required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    residente = forms.ModelChoiceField(label='Residente (opcional)', required=False, queryset=Residente.objects.none(),
                                       empty_label='— Aviso general del hogar —',
                                       widget=forms.Select(attrs={'class': 'form-select'}))
    gravedad = forms.ChoiceField(label='Importancia', initial=Alerta.MEDIA, widget=forms.Select(attrs={'class': 'form-select'}),
                                 choices=[(Alerta.ALTA, 'Alta'), (Alerta.MEDIA, 'Media'), (Alerta.INFORMATIVA, 'Informativa')])
    roles = forms.MultipleChoiceField(label='Para quién', choices=ROLES_ELEGIBLES,
                                      widget=forms.CheckboxSelectMultiple)
    horas = forms.TypedChoiceField(label='Vigencia', choices=VIGENCIAS, coerce=int, initial=24,
                                   widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, hogar=None, **kwargs):
        super().__init__(*args, **kwargs)
        residentes = sorted(Residente.objects.filter(hogar=hogar, activo=True), key=lambda r: r.get_nombre())
        self.fields['residente'].queryset = Residente.objects.filter(hogar=hogar, activo=True)
        self.fields['residente'].choices = [('', '— Aviso general del hogar —')] + [(r.pk, r.get_nombre()) for r in residentes]


class AtenderForm(forms.Form):
    nota = forms.CharField(label='Qué se hizo', required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))


class DescartarForm(forms.Form):
    motivo = forms.CharField(label='Por qué no aplica', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))


class ConfiguracionForm(forms.Form):
    def __init__(self, *args, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        for codigo, (_f, nombre) in REGLAS.items():
            self.fields[f'regla_{codigo}'] = forms.BooleanField(
                label=nombre, required=False, initial=config.regla_activa(codigo),
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            )
        for nombre, datos in UMBRALES.items():
            self.fields[f'umbral_{nombre}'] = forms.IntegerField(
                label=datos['etiqueta'], min_value=0, max_value=1000, initial=config.umbral(nombre),
                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'max-width:110px'}),
            )

    def campos_reglas(self):
        return [self[f'regla_{c}'] for c in REGLAS]

    def campos_umbrales(self):
        return [self[f'umbral_{n}'] for n in UMBRALES]

    def guardar(self):
        self.config.reglas_desactivadas = [c for c in REGLAS if not self.cleaned_data[f'regla_{c}']]
        self.config.umbrales = {n: self.cleaned_data[f'umbral_{n}'] for n in UMBRALES}
        self.config.ultima_evaluacion = None  # que se reevalúe con lo nuevo
        self.config.save()
        return self.config
