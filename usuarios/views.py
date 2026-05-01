from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .decorators import administrador_requerido
from auditoria.models import RegistroAuditoria
from .models import Usuario, Rol
from .forms import UsuarioCrearForm, UsuarioEditarForm




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

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
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
            try:
                from usuarios.models import Usuario
                Usuario.objects.get(username=username)
                registrar_auditoria(
                    usuario=None,
                    accion=RegistroAuditoria.INICIO_SESION,
                    descripcion=f'Intento de login fallido para usuario: {username}',
                    request=request
                )
            except Exception:
                pass

    return render(request, 'usuarios/login.html', {'error': error})


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
    hogar = request.user.hogar
    contexto = {}

    if hogar:
        from residentes.models import Residente
        from infraestructura.models import Cama
        from notas_clinicas.models import NotaClinica
        from django.utils import timezone
        from datetime import timedelta

        hoy = timezone.now().date()

        # Residentes
        total_residentes = Residente.objects.filter(hogar=hogar, activo=True).count()
        ingresos_mes = Residente.objects.filter(
            hogar=hogar,
            fecha_ingreso__month=hoy.month,
            fecha_ingreso__year=hoy.year
        ).count()

        # Camas
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

        # Notas hoy
        notas_hoy = NotaClinica.objects.filter(
            residente__hogar=hogar,
            fecha_creacion__date=hoy
        ).count()

        # Notas últimos 7 días
        notas_semana = NotaClinica.objects.filter(
            residente__hogar=hogar,
            fecha_creacion__date__gte=hoy - timedelta(days=7)
        ).count()

        contexto = {
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
    hogar = request.user.hogar
    usuarios = Usuario.objects.filter(hogar=hogar).order_by('last_name', 'first_name')
    return render(request, 'usuarios/usuario_lista.html', {
        'usuarios': usuarios
    })


@login_required
@administrador_requerido
def usuario_crear(request):
    form = UsuarioCrearForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        usuario = form.save(commit=False)
        usuario.hogar = request.user.hogar
        usuario.set_password(form.cleaned_data['password1'])
        usuario.save()
        messages.success(request, f'Usuario {usuario.username} creado correctamente.')
        return redirect('usuario_lista')
    return render(request, 'usuarios/usuario_form.html', {
        'form': form,
        'titulo': 'Nuevo Usuario',
        'accion': 'Crear'
    })


@login_required
@administrador_requerido
def usuario_editar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk, hogar=request.user.hogar)
    form = UsuarioEditarForm(request.POST or None, instance=usuario, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
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
    usuario = get_object_or_404(Usuario, pk=pk, hogar=request.user.hogar)
    if usuario == request.user:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('usuario_lista')
    usuario.activo = not usuario.activo
    usuario.is_active = usuario.activo
    usuario.save()
    estado = 'activado' if usuario.activo else 'desactivado'
    messages.success(request, f'Usuario {estado} correctamente.')
    return redirect('usuario_lista')