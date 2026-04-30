from django.urls import path
from . import views

urlpatterns = [
    # Departamentos
    path('departamentos/', views.departamento_lista, name='departamento_lista'),
    path('departamentos/nuevo/', views.departamento_crear, name='departamento_crear'),
    path('departamentos/<int:pk>/editar/', views.departamento_editar, name='departamento_editar'),
    path('departamentos/<int:pk>/desactivar/', views.departamento_desactivar, name='departamento_desactivar'),

    # Habitaciones
    path('habitaciones/', views.habitacion_lista, name='habitacion_lista'),
    path('habitaciones/nueva/', views.habitacion_crear, name='habitacion_crear'),
    path('habitaciones/<int:pk>/editar/', views.habitacion_editar, name='habitacion_editar'),
    path('habitaciones/<int:pk>/desactivar/', views.habitacion_desactivar, name='habitacion_desactivar'),

    # Camas
    path('camas/', views.cama_lista, name='cama_lista'),
    path('camas/nueva/', views.cama_crear, name='cama_crear'),
    path('camas/<int:pk>/editar/', views.cama_editar, name='cama_editar'),
    path('camas/<int:pk>/desactivar/', views.cama_desactivar, name='cama_desactivar'),
]