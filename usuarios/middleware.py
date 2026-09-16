from django.shortcuts import redirect
from django.urls import reverse


class ForzarCambioPasswordMiddleware:
    """Si el usuario autenticado tiene `debe_cambiar_password=True` (por
    ejemplo, tras un restablecimiento de contraseña hecho por un
    administrador — ver usuarios.views.usuario_resetear_password), lo
    redirige a la pantalla de "Cambiar contraseña" en cualquier otra
    solicitud, hasta que la cambie voluntariamente (lo que limpia el flag,
    ver usuarios.views.cambiar_password).

    Se comprueba en CADA solicitud (no solo en el login): como Django
    recarga request.user desde la base de datos en cada request, esto
    también atrapa una sesión que ya estaba iniciada en el momento en que
    un administrador restableció la contraseña — no depende de que el
    usuario vuelva a iniciar sesión para activarse.

    No debe producir un bucle de redirección: la propia pantalla de
    cambio de contraseña y el cierre de sesión quedan siempre accesibles,
    igual que /admin/ y los archivos estáticos (para no interferir con el
    panel de administración de Django ni con el servido de estáticos en
    desarrollo).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user is not None
            and getattr(user, 'is_authenticated', False)
            and getattr(user, 'debe_cambiar_password', False)
            and request.path not in (reverse('cambiar_password'), reverse('logout'))
            and not request.path.startswith('/admin/')
            and not request.path.startswith('/static/')
        ):
            return redirect('cambiar_password')
        return self.get_response(request)
