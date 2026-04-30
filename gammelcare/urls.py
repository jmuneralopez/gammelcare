from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('usuarios/', include('usuarios.urls')),
    path('infraestructura/', include('infraestructura.urls')),
    path('residentes/', include('residentes.urls')),
    path('catalogos/', include('catalogos.urls')),
    path('notas/', include('notas_clinicas.urls')),
    path('', lambda request: redirect('login'), name='home'),
]