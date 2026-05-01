from django.urls import path
from . import views

urlpatterns = [
    # Búsquedas Select2
    path('buscar/cie10/', views.buscar_cie10, name='buscar_cie10'),
    path('buscar/eps/', views.buscar_eps, name='buscar_eps'),
    path('buscar/ambulancia/', views.buscar_ambulancia, name='buscar_ambulancia'),

    # EPS
    path('eps/', views.eps_lista, name='eps_lista'),
    path('eps/nueva/', views.eps_crear, name='eps_crear'),
    path('eps/<int:pk>/editar/', views.eps_editar, name='eps_editar'),

    # Ambulancia
    path('ambulancia/', views.ambulancia_lista, name='ambulancia_lista'),
    path('ambulancia/nueva/', views.ambulancia_crear, name='ambulancia_crear'),
    path('ambulancia/<int:pk>/editar/', views.ambulancia_editar, name='ambulancia_editar'),
]