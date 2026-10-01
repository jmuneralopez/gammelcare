from datetime import timedelta

from django import forms
from django.utils import timezone

from . import parametros as P
from .models import ControlSignos, RangoResidente, RegistroLiquidos

FMT = '%Y-%m-%dT%H:%M'
HORAS_REGISTRO_TARDIO = 72


def _fecha_hora():
    return forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format=FMT)


def _validar_fecha_toma(valor):
    ahora = timezone.now()
    if valor > ahora + timedelta(minutes=5):
        raise forms.ValidationError('La hora de la toma no puede ser futura.')
    if valor < ahora - timedelta(hours=HORAS_REGISTRO_TARDIO):
        raise forms.ValidationError(f'Solo se registran tomas de las últimas {HORAS_REGISTRO_TARDIO} horas.')
    return valor


def _num(attrs=None):
    base = {'class': 'form-control', 'inputmode': 'decimal'}
    base.update(attrs or {})
    return forms.NumberInput(attrs=base)


class ControlForm(forms.ModelForm):
    class Meta:
        model = ControlSignos
        fields = ['fecha_hora', 'pas', 'pad', 'fc', 'fr', 'temperatura', 'spo2', 'oxigeno_suplementario',
                  'litros_oxigeno', 'glucometria', 'momento_glucometria', 'dolor', 'peso', 'observaciones']
        widgets = {
            'fecha_hora': _fecha_hora(),
            # Sin números de ejemplo: en una casilla de signos un "120" gris se confunde con un valor tomado.
            'pas': _num(), 'pad': _num(), 'fc': _num(), 'fr': _num(),
            'temperatura': _num({'step': '0.1'}),
            'spo2': _num(),
            'oxigeno_suplementario': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'litros_oxigeno': _num({'step': '0.5'}),
            'glucometria': _num(),
            'momento_glucometria': forms.Select(attrs={'class': 'form-select'}),
            'dolor': _num({'min': 0, 'max': 10}),
            'peso': _num({'step': '0.1'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                                   'placeholder': 'Ej.: tomada sentado, después del almuerzo.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_hora'].input_formats = [FMT]
        self.fields['momento_glucometria'].choices = [('', '—')] + ControlSignos.MOMENTOS_GLUCOMETRIA
        if not self.is_bound:
            self.initial.setdefault('fecha_hora', timezone.localtime().replace(second=0, microsecond=0))

    def clean_fecha_hora(self):
        return _validar_fecha_toma(self.cleaned_data['fecha_hora'])

    def clean(self):
        datos = super().clean()
        for p in P.PARAMETROS:
            v = datos.get(p.codigo)
            if v is not None and not (p.minimo_posible <= v <= p.maximo_posible):
                self.add_error(p.codigo, f'Revise el valor: {p.nombre.lower()} debe estar entre '
                                         f'{p.minimo_posible} y {p.maximo_posible} {p.unidad}.')
        peso = datos.get('peso')
        if peso is not None and not (20 <= peso <= 250):
            self.add_error('peso', 'Revise el peso: debe estar entre 20 y 250 kg.')
        if not any(datos.get(c) is not None for c in P.CODIGOS + ['peso']):
            raise forms.ValidationError('Registre al menos un signo vital o el peso.')
        pas, pad = datos.get('pas'), datos.get('pad')
        if (pas is None) != (pad is None):
            self.add_error('pas' if pas is None else 'pad', 'Registre la presión completa (sistólica y diastólica).')
        elif pas is not None and pad >= pas:
            self.add_error('pad', 'La diastólica debe ser menor que la sistólica.')
        if datos.get('oxigeno_suplementario') and not datos.get('litros_oxigeno'):
            self.add_error('litros_oxigeno', 'Indique los litros por minuto.')
        if not datos.get('oxigeno_suplementario'):
            datos['litros_oxigeno'] = None
        if datos.get('glucometria') is not None and not datos.get('momento_glucometria'):
            self.add_error('momento_glucometria', 'Indique en qué momento se tomó la glucometría.')
        return datos


class LiquidosForm(forms.ModelForm):
    class Meta:
        model = RegistroLiquidos
        fields = ['fecha_hora', 'via', 'cantidad_ml', 'observaciones']
        widgets = {
            'fecha_hora': _fecha_hora(),
            'via': forms.Select(attrs={'class': 'form-select'}),
            'cantidad_ml': _num({'min': 1}),
            'observaciones': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_hora'].input_formats = [FMT]
        if not self.is_bound:
            self.initial.setdefault('fecha_hora', timezone.localtime().replace(second=0, microsecond=0))

    def clean_fecha_hora(self):
        return _validar_fecha_toma(self.cleaned_data['fecha_hora'])

    def clean_cantidad_ml(self):
        v = self.cleaned_data['cantidad_ml']
        if not 1 <= v <= 5000:
            raise forms.ValidationError('Revise la cantidad: entre 1 y 5000 mL.')
        return v

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tipo = RegistroLiquidos.INGRESO if obj.via in RegistroLiquidos.VIAS_INGRESO else RegistroLiquidos.EGRESO
        if commit:
            obj.save()
        return obj


class AnularForm(forms.Form):
    motivo = forms.CharField(label='Motivo de la anulación', widget=forms.Textarea(attrs={
        'class': 'form-control', 'rows': 2, 'placeholder': 'Ej.: se registró en el residente equivocado.'}))


def _validar_orden(datos, form):
    orden = [datos.get('critico_min'), datos.get('normal_min'), datos.get('normal_max'), datos.get('critico_max')]
    presentes = [v for v in orden if v is not None]
    if presentes != sorted(presentes):
        form.add_error(None, 'Los límites deben ir de menor a mayor: crítico bajo ≤ mínimo normal ≤ máximo normal ≤ crítico alto.')


class RangoResidenteForm(forms.ModelForm):
    class Meta:
        model = RangoResidente
        fields = ['parametro', 'critico_min', 'normal_min', 'normal_max', 'critico_max', 'motivo']
        widgets = {
            'parametro': forms.Select(attrs={'class': 'form-select'}),
            'critico_min': _num({'step': 'any'}), 'normal_min': _num({'step': 'any'}),
            'normal_max': _num({'step': 'any'}), 'critico_max': _num({'step': 'any'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                            'placeholder': 'Ej.: EPOC; meta de saturación 88 a 92 %.'}),
        }
        labels = {'parametro': 'Signo vital', 'critico_min': 'Crítico si es menor que',
                  'normal_min': 'Mínimo normal', 'normal_max': 'Máximo normal',
                  'critico_max': 'Crítico si es mayor que'}

    def clean(self):
        datos = super().clean()
        _validar_orden(datos, self)
        if not any(datos.get(k) is not None for k in ('critico_min', 'normal_min', 'normal_max', 'critico_max')):
            raise forms.ValidationError('Indique al menos un límite.')
        return datos


class RangosHogarForm(forms.Form):
    LIMITES = [('critico_min', 'Crítico <'), ('normal_min', 'Mín. normal'),
               ('normal_max', 'Máx. normal'), ('critico_max', 'Crítico >')]

    def __init__(self, *args, rangos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filas = []
        for p in P.PARAMETROS:
            actual = rangos.rango(p.codigo)
            campos = []
            for limite, etiqueta in self.LIMITES:
                nombre = f'{p.codigo}__{limite}'
                self.fields[nombre] = forms.DecimalField(
                    label=etiqueta, required=False, max_digits=6, decimal_places=1, initial=actual[limite],
                    widget=_num({'step': 'any', 'class': 'form-control form-control-sm'}),
                )
                campos.append(nombre)
            self.filas.append((p, campos))

    def clean(self):
        datos = super().clean()
        for p, campos in self.filas:
            valores = [datos.get(c) for c in campos]
            presentes = [v for v in valores if v is not None]
            if presentes != sorted(presentes):
                self.add_error(campos[0], f'{p.nombre}: los límites deben ir de menor a mayor.')
        return datos

    def como_json(self):
        salida = {}
        for p, campos in self.filas:
            valores = {c.split('__')[1]: self.cleaned_data.get(c) for c in campos}
            if any(valores[k] != v for k, v in P.rango_por_defecto(p.codigo).items()):
                salida[p.codigo] = {k: (None if v is None else str(v)) for k, v in valores.items()}
        return salida
