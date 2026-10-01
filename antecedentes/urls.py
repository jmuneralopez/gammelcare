from django.urls import path

from . import views

urlpatterns = [
    path('residente/<int:pk>/', views.residente_antecedentes, name='residente_antecedentes'),
    path('residente/<int:pk>/alergia/nueva/', views.alergia_crear, name='alergia_crear'),
    path('residente/<int:pk>/antecedente/nuevo/', views.antecedente_crear, name='antecedente_crear'),
    path('residente/<int:pk>/sin-alergias/', views.declarar_sin_alergias, name='declarar_sin_alergias'),
    path('alergia/<int:pk>/inactivar/', views.alergia_inactivar, name='alergia_inactivar'),
    path('antecedente/<int:pk>/inactivar/', views.antecedente_inactivar, name='antecedente_inactivar'),
]
