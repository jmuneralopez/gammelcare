from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from auditoria.models import RegistroAuditoria


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
    return render(request, 'usuarios/dashboard.html')