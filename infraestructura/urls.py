from django.urls import path

from . import views

urlpatterns = [
    path('institucion/', views.institucion, name='institucion'),

    # Las listas anteriores redirigen a Institución.
    path('departamentos/', views.lista_anterior, name='departamento_lista'),
    path('habitaciones/', views.lista_anterior, name='habitacion_lista'),
    path('camas/', views.lista_anterior, name='cama_lista'),

    path('departamentos/nuevo/', views.departamento_crear, name='departamento_crear'),
    path('departamentos/nuevo-rapido/', views.departamento_crear_rapido, name='departamento_crear_rapido'),
    path('departamentos/<int:pk>/editar/', views.departamento_editar, name='departamento_editar'),
    path('departamentos/<int:pk>/desactivar/', views.departamento_desactivar, name='departamento_desactivar'),

    path('habitaciones/nueva/', views.habitacion_crear, name='habitacion_crear'),
    path('habitaciones/nueva-rapida/', views.habitacion_crear_rapido, name='habitacion_crear_rapido'),
    path('habitaciones/<int:pk>/editar/', views.habitacion_editar, name='habitacion_editar'),
    path('habitaciones/<int:pk>/desactivar/', views.habitacion_desactivar, name='habitacion_desactivar'),

    path('camas/nueva/', views.cama_crear, name='cama_crear'),
    path('camas/<int:pk>/editar/', views.cama_editar, name='cama_editar'),
    path('camas/<int:pk>/desactivar/', views.cama_desactivar, name='cama_desactivar'),
]
