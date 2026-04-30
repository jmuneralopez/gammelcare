from django.urls import path
from . import views

urlpatterns = [
    path('buscar/cie10/', views.buscar_cie10, name='buscar_cie10'),
    path('buscar/eps/', views.buscar_eps, name='buscar_eps'),
    path('buscar/ambulancia/', views.buscar_ambulancia, name='buscar_ambulancia'),
]