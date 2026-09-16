import secrets

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .decorators import administrador_requerido
from auditoria.models import RegistroAuditoria
from .models import Usuario, Rol
from .forms import UsuarioCrearForm, UsuarioEditarForm


def _usuario_gestionable_or_404(request, pk):
    """Usuario objetivo de una acción de gestión (editar, activar/desactivar,
    restablecer contraseña): el superadmin puede gestionar usuarios de
    cualquier hogar, el administrador del hogar solo los de su propio
    hogar. Misma regla para las tres acciones, para que compartan
    consistentemente el mismo alcance."""
    if request.user.es_superadmin():
        return get_object_or_404(Usuario, pk=pk)
    return get_object_or_404(
        Usuario.objects.exclude(roles__nombre=Rol.SUPERADMIN),
        pk=pk, hogar=request.user.hogar
    )

def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def registrar_auditoria(usuario, accion, descripcion, request):
    RegistroAuditoria.objects.create(
        usuario=usuario,
        accion=accion,
        descripcion=descripcion,
        ip_address=get_client_ip(request)
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    error = False
    mensaje_error = None

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        usuario_existente = Usuario.objects.filter(username=username).first()

        # Cuenta ya bloqueada por intentos previos: ni siquiera se valida la contraseña
        if usuario_existente and usuario_existente.esta_bloqueado():
            from django.utils import timezone
            minutos = max(1, int((usuario_existente.bloqueado_hasta - timezone.now()).total_seconds() // 60) + 1)
            error = True
            mensaje_error = (
                f'Esta cuenta está bloqueada temporalmente por múltiples intentos fallidos. '
                f'Intenta de nuevo en {minutos} minuto(s) o contacta al administrador.'
            )
            registrar_auditoria(
                usuario=None,
                accion=RegistroAuditoria.INICIO_SESION,
                descripcion=f'Intento de login rechazado por bloqueo temporal: {username}',
                request=request
            )
            return render(request, 'usuarios/login.html', {'error': error, 'mensaje_error': mensaje_error})

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.hogar and not user.hogar.activo:
                mensaje_error = 'El hogar al que perteneces está desactivado. Contacta al administrador del sistema.'
                return render(request, 'usuarios/login.html', {'error': True, 'mensaje_error': mensaje_error})
            user.resetear_intentos()
            login(request, user)
            registrar_auditoria(
                usuario=user,
                accion=RegistroAuditoria.INICIO_SESION,
                descripcion=f'Inicio de sesión exitoso: {user.username}',
                request=request
            )
            return redirect('dashboard')
        else:
            error = True
            if usuario_existente:
                usuario_existente.registrar_intento_fallido()
                if usuario_existente.esta_bloqueado():
                    mensaje_error = (
                        'Cuenta bloqueada temporalmente por múltiples intentos fallidos. '
                        'Intenta de nuevo más tarde o contacta al administrador.'
                    )
                    descripcion = f'Cuenta bloqueada tras intentos fallidos repetidos: {username}'
                else:
                    descripcion = f'Intento de login fallido para usuario: {username}'
                registrar_auditoria(
                    usuario=None,
                    accion=RegistroAuditoria.INICIO_SESION,
                    descripcion=descripcion,
                    request=request
                )

    return render(request, 'usuarios/login.html', {'error': error, 'mensaje_error': mensaje_error})


@login_required
def logout_view(request):
    registrar_auditoria(
        usuario=request.user,
        accion=RegistroAuditoria.CIERRE_SESION,
        descripcion=f'Cierre de sesión: {request.user.username}',
        request=request
    )
    logout(request)
    messages.success(request, 'Sesión cerrada correctamente.')
    return redirect('login')


@login_required
def dashboard_view(request):
    from django.utils import timezone
    from datetime import timedelta
    from residentes.models import Residente
    from infraestructura.models import Cama
    from notas_clinicas.models import NotaClinica
    from hogares.models import Hogar

    hoy = timezone.now().date()
    contexto = {}

    if request.user.es_superadmin():
        # ── Estadísticas globales ──────────────────────
        total_hogares = Hogar.objects.filter(activo=True).count()
        total_hogares_registrados = Hogar.objects.count()
        total_hogares_pausados = total_hogares_registrados - total_hogares
        total_usuarios_activos = Usuario.objects.filter(activo=True).count()
        total_residentes = Residente.objects.filter(activo=True).count()
        total_camas_ocupadas = Cama.objects.filter(estado='ocupada', activo=True).count()
        total_notas_hoy = NotaClinica.objects.filter(
            fecha_creacion__date=hoy
        ).count()

        # ── Por hogar ──────────────────────────────────
        hogares_data = []
        for hogar in Hogar.objects.filter(activo=True).order_by('nombre'):
            residentes = Residente.objects.filter(hogar=hogar, activo=True).count()
            camas_total = Cama.objects.filter(
                habitacion__departamento__hogar=hogar, activo=True
            ).count()
            camas_ocupadas = Cama.objects.filter(
                habitacion__departamento__hogar=hogar,
                activo=True, estado='ocupada'
            ).count()
            notas_hoy = NotaClinica.objects.filter(
                residente__hogar=hogar,
                fecha_creacion__date=hoy
            ).count()
            notas_semana = NotaClinica.objects.filter(
                residente__hogar=hogar,
                fecha_creacion__date__gte=hoy - timedelta(days=7)
            ).count()
            pct = round((camas_ocupadas / camas_total * 100)) if camas_total > 0 else 0
            color = 'danger' if pct >= 80 else 'warning' if pct >= 50 else 'success'

            hogares_data.append({
                'hogar': hogar,
                'residentes': residentes,
                'camas_total': camas_total,
                'camas_ocupadas': camas_ocupadas,
                'notas_hoy': notas_hoy,
                'notas_semana': notas_semana,
                'pct': pct,
                'color': color,
            })

        contexto = {
            'es_superadmin': True,
            'total_hogares': total_hogares,
            'total_hogares_registrados': total_hogares_registrados,
            'total_hogares_pausados': total_hogares_pausados,
            'total_usuarios_activos': total_usuarios_activos,
            'total_residentes': total_residentes,
            'total_camas_ocupadas': total_camas_ocupadas,
            'total_notas_hoy': total_notas_hoy,
            'hogares_data': hogares_data,
        }

    elif request.user.hogar:
        hogar = request.user.hogar
        total_residentes = Residente.objects.filter(hogar=hogar, activo=True).count()
        ingresos_mes = Residente.objects.filter(
            hogar=hogar,
            fecha_ingreso__month=hoy.month,
            fecha_ingreso__year=hoy.year
        ).count()
        total_camas = Cama.objects.filter(
            habitacion__departamento__hogar=hogar, activo=True
        ).count()
        camas_disponibles = Cama.objects.filter(
            habitacion__departamento__hogar=hogar,
            activo=True, estado='disponible'
        ).count()
        camas_ocupadas = Cama.objects.filter(
            habitacion__departamento__hogar=hogar,
            activo=True, estado='ocupada'
        ).count()
        ocupacion_pct = round((camas_ocupadas / total_camas * 100), 1) if total_camas > 0 else 0
        notas_hoy = NotaClinica.objects.filter(
            residente__hogar=hogar,
            fecha_creacion__date=hoy
        ).count()
        notas_semana = NotaClinica.objects.filter(
            residente__hogar=hogar,
            fecha_creacion__date__gte=hoy - timedelta(days=7)
        ).count()

        contexto = {
            'es_superadmin': False,
            'total_residentes': total_residentes,
            'ingresos_mes': ingresos_mes,
            'total_camas': total_camas,
            'camas_disponibles': camas_disponibles,
            'camas_ocupadas': camas_ocupadas,
            'ocupacion_pct': ocupacion_pct,
            'notas_hoy': notas_hoy,
            'notas_semana': notas_semana,
        }

    return render(request, 'usuarios/dashboard.html', contexto)

@login_required
@administrador_requerido
def usuario_lista(request):
    if request.user.es_superadmin():
        # Superadmin ve todos los usuarios agrupados por hogar
        hogar_id = request.GET.get('hogar', '')
        from hogares.models import Hogar
        hogares = Hogar.objects.all().order_by('nombre')
        usuarios = Usuario.objects.all().order_by('hogar__nombre', 'last_name')
        if hogar_id:
            usuarios = usuarios.filter(hogar_id=hogar_id)
        return render(request, 'usuarios/usuario_lista_superadmin.html', {
            'usuarios': usuarios,
            'hogares': hogares,
            'hogar_seleccionado': hogar_id,
        })
    else:
        # Administrador ve solo usuarios de su hogar (nunca a un superadmin,
        # aunque por algún motivo tenga ese hogar asignado)
        hogar = request.user.hogar
        usuarios = Usuario.objects.filter(hogar=hogar).exclude(
            roles__nombre=Rol.SUPERADMIN
        ).order_by('last_name', 'first_name')
        return render(request, 'usuarios/usuario_lista.html', {
            'usuarios': usuarios
        })


@login_required
@administrador_requerido
def usuario_crear(request):
    form = UsuarioCrearForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        usuario = form.save(commit=False)
        if request.user.es_superadmin():
            usuario.hogar = form.cleaned_data.get('hogar')
        else:
            usuario.hogar = request.user.hogar
        usuario.set_password(form.cleaned_data['password1'])
        usuario.save()
        form.save_m2m()
        if getattr(form, 'hogar_auto_corregido', False):
            messages.info(
                request,
                'El rol "Superadministrador" no puede tener un hogar asignado, '
                'así que el usuario se creó sin hogar.'
            )
        messages.success(request, f'Usuario {usuario.username} creado correctamente.')
        return redirect('usuario_lista')
    return render(request, 'usuarios/usuario_form.html', {
        'form': form,
        'titulo': 'Nuevo Usuario',
        'accion': 'Crear'
    })


def _hogar_se_quedaria_sin_administrador(hogar_id, excluyendo_pk):
    """True si, excluyendo al usuario `excluyendo_pk`, el hogar `hogar_id`
    no tiene ningún OTRO usuario activo con el rol administrador. Se usa
    para bloquear ediciones/desactivaciones que dejarían un hogar sin
    ningún administrador activo. No aplica a un hogar que nunca tuvo
    administrador (ese es un estado inicial normal, no una regresión)."""
    return not Usuario.objects.filter(
        hogar_id=hogar_id, roles__nombre=Rol.ADMINISTRADOR, activo=True
    ).exclude(pk=excluyendo_pk).exists()


@login_required
@administrador_requerido
def usuario_editar(request, pk):
    usuario = _usuario_gestionable_or_404(request, pk)
    # Estado ANTES de tocar el formulario: is_valid() mutará atributos del
    # propio `usuario` (es la misma instancia que form.instance) para los
    # campos que sí están en Meta.fields, así que hay que capturar esto
    # antes de esa llamada.
    era_administrador_activo_del_hogar = bool(
        usuario.hogar_id and usuario.activo and usuario.tiene_rol(Rol.ADMINISTRADOR)
    )
    hogar_id_original = usuario.hogar_id

    form = UsuarioEditarForm(request.POST or None, instance=usuario, user=request.user)
    if request.method == 'POST' and form.is_valid():
        nuevos_roles = form.cleaned_data.get('roles') or []
        nuevo_activo = form.cleaned_data.get('activo')
        seguira_siendo_administrador_activo = bool(
            nuevo_activo and any(r.nombre == Rol.ADMINISTRADOR for r in nuevos_roles)
        )

        if (era_administrador_activo_del_hogar
                and not seguira_siendo_administrador_activo
                and _hogar_se_quedaria_sin_administrador(hogar_id_original, usuario.pk)):
            messages.error(
                request,
                'No puedes quitar el rol de Administrador (ni desactivar la cuenta) '
                'a este usuario: es el último administrador activo de su hogar. '
                'Asigna otro administrador antes de hacer este cambio.'
            )
            return render(request, 'usuarios/usuario_form.html', {
                'form': form,
                'titulo': 'Editar Usuario',
                'accion': 'Guardar cambios',
                'usuario': usuario
            })

        form.save()
        if getattr(form, 'hogar_auto_corregido', False):
            messages.info(
                request,
                'El rol "Superadministrador" no puede tener un hogar asignado, '
                'así que se quitó el hogar de este usuario.'
            )
        messages.success(request, 'Usuario actualizado correctamente.')
        return redirect('usuario_lista')
    return render(request, 'usuarios/usuario_form.html', {
        'form': form,
        'titulo': 'Editar Usuario',
        'accion': 'Guardar cambios',
        'usuario': usuario
    })

@login_required
@administrador_requerido
def usuario_toggle(request, pk):
    usuario = _usuario_gestionable_or_404(request, pk)
    if usuario == request.user:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('usuario_lista')

    va_a_desactivarse = usuario.activo
    if (va_a_desactivarse
            and usuario.hogar_id
            and usuario.tiene_rol(Rol.ADMINISTRADOR)
            and _hogar_se_quedaria_sin_administrador(usuario.hogar_id, usuario.pk)):
        messages.error(
            request,
            'No puedes desactivar a este usuario: es el último administrador '
            'activo de su hogar. Asigna otro administrador antes de desactivarlo.'
        )
        return redirect('usuario_lista')

    usuario.activo = not usuario.activo
    usuario.is_active = usuario.activo
    usuario.save()
    estado = 'activado' if usuario.activo else 'desactivado'
    messages.success(request, f'Usuario {estado} correctamente.')
    return redirect('usuario_lista')


@login_required
@administrador_requerido
def usuario_resetear_password(request, pk):
    """Genera una contraseña temporal para `pk`, la fuerza a cambiarla en
    su próximo inicio de sesión y la muestra UNA sola vez en pantalla.
    Reutiliza exactamente el mismo alcance de gestión que usuario_editar
    y usuario_toggle (_usuario_gestionable_or_404)."""
    usuario = _usuario_gestionable_or_404(request, pk)
    if usuario == request.user:
        messages.error(
            request,
            'No puedes restablecer la contraseña de tu propia cuenta desde aquí. '
            'Usa la opción "Cambiar contraseña" del menú de tu perfil.'
        )
        return redirect('usuario_lista')

    # Alfabeto legible: sin caracteres fácilmente confundibles (0/O, 1/l/I).
    alfabeto = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    password_temporal = ''.join(secrets.choice(alfabeto) for _ in range(12))

    usuario.set_password(password_temporal)
    usuario.debe_cambiar_password = True
    usuario.save(update_fields=['password', 'debe_cambiar_password'])

    # La contraseña en texto plano NUNCA se registra en la auditoría.
    registrar_auditoria(
        usuario=request.user,
        accion=RegistroAuditoria.RESETEO_PASSWORD,
        descripcion=(
            f'{request.user.username} restableció la contraseña del usuario '
            f'{usuario.username} y le asignó una contraseña temporal.'
        ),
        request=request
    )

    return render(request, 'usuarios/usuario_password_temporal.html', {
        'usuario': usuario,
        'password_temporal': password_temporal,
    })


@login_required
def cambiar_password(request):
    if request.method == 'POST':
        password_actual = request.POST.get('password_actual')
        password_nueva = request.POST.get('password_nueva')
        password_confirmar = request.POST.get('password_confirmar')

        if not request.user.check_password(password_actual):
            messages.error(request, 'La contraseña actual es incorrecta.')
        elif password_nueva != password_confirmar:
            messages.error(request, 'Las contraseñas nuevas no coinciden.')
        elif len(password_nueva) < 8:
            messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')
        else:
            request.user.set_password(password_nueva)
            request.user.debe_cambiar_password = False
            request.user.save()
            messages.success(request, 'Contraseña cambiada correctamente. Por favor inicia sesión nuevamente.')
            return redirect('login')

    return render(request, 'usuarios/cambiar_password.html')