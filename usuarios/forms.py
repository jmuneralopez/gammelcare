from django import forms
from .models import Usuario, Rol
from hogares.models import Hogar


class UsuarioCrearForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contraseña'
        })
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Repita la contraseña'
        })
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=Rol.objects.all(),
        widget=forms.CheckboxSelectMultiple(),
        label='Roles',
        required=True
    )
    hogar = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Hogar',
        empty_label='Sin hogar asignado'
    )

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'username', 'email', 'roles']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombres'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellidos'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Usuario para login'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Correo electrónico'}),
        }
        labels = {
            'first_name': 'Nombres',
            'last_name': 'Apellidos',
            'username': 'Usuario',
            'email': 'Correo electrónico',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from hogares.models import Hogar
        if user and user.es_superadmin():
            self.fields['hogar'].queryset = Hogar.objects.filter(activo=True)
            self.fields['roles'].queryset = Rol.objects.all()
        elif user and user.tiene_rol(Rol.ADMINISTRADOR):
            self.fields['hogar'].queryset = Hogar.objects.none()
            self.fields['hogar'].widget = forms.HiddenInput()
            self.fields['roles'].queryset = Rol.objects.filter(
                nombre__in=[Rol.ADMINISTRADOR] + Rol.ROLES_CLINICOS
            )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')

        roles = cleaned_data.get('roles')
        if roles and any(r.nombre == Rol.SUPERADMIN for r in roles) and cleaned_data.get('hogar'):
            # Un superadmin no debe quedar asignado a un hogar: eso le
            # daría visibilidad/gestión cruzada con el administrador de
            # ese hogar. Se corrige automáticamente (no se bloquea el
            # formulario) y se marca `hogar_auto_corregido` para que la
            # vista pueda avisarle al usuario con un mensaje claro.
            cleaned_data['hogar'] = None
            self.hogar_auto_corregido = True
        return cleaned_data


class UsuarioEditarForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        queryset=Rol.objects.all(),
        widget=forms.CheckboxSelectMultiple(),
        label='Roles',
        required=True
    )
    hogar = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Hogar',
        empty_label='Sin hogar asignado'
    )

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'email', 'roles', 'activo', 'hogar']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'first_name': 'Nombres',
            'last_name': 'Apellidos',
            'email': 'Correo electrónico',
            'activo': 'Usuario activo',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.es_superadmin():
            # Solo el superadmin puede reasignar el hogar de un usuario ya
            # creado (p. ej. para corregir una cuenta que quedó sin hogar).
            self.fields['hogar'].queryset = Hogar.objects.filter(activo=True)
        else:
            # Un administrador de hogar no gestiona hogares ajenos: se quita
            # el campo por completo (no solo se oculta) para que _post_clean()
            # nunca lo toque y el hogar actual del usuario no se pierda.
            del self.fields['hogar']
        if user and user.tiene_rol(Rol.ADMINISTRADOR):
            self.fields['roles'].queryset = Rol.objects.filter(
                nombre__in=[Rol.ADMINISTRADOR] + Rol.ROLES_CLINICOS
            )

    def clean(self):
        cleaned_data = super().clean()
        roles = cleaned_data.get('roles')
        if roles and any(r.nombre == Rol.SUPERADMIN for r in roles):
            # Un superadmin no debe quedar asignado a un hogar. Se corrige en
            # cleaned_data (si el campo está presente, i.e. quien edita es
            # superadmin) y también directamente sobre self.instance (para
            # cuando el campo no está en el formulario, i.e. quien edita es
            # administrador y el usuario ya tenía hogar de alguna otra forma).
            if 'hogar' in cleaned_data:
                cleaned_data['hogar'] = None
            if self.instance.hogar_id:
                self.instance.hogar = None
            self.hogar_auto_corregido = True
        return cleaned_data