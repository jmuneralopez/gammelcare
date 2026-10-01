from django.urls import path
from . import views

urlpatterns = [
    # Catálogo
    path('buscar/', views.buscar_medicamento, name='buscar_medicamento'),
    path('crear-rapido/', views.medicamento_crear_rapido, name='medicamento_crear_rapido'),

    # Tratamientos (Prescripcion)
    path('residente/<int:pk>/tratamientos/', views.tratamiento_lista, name='tratamiento_lista'),
    path('residente/<int:pk>/tratamientos/nuevo/', views.tratamiento_crear, name='tratamiento_crear'),
    path('tratamiento/<int:pk>/', views.tratamiento_detalle, name='tratamiento_detalle'),
    path('tratamiento/<int:pk>/suspender/', views.tratamiento_suspender, name='tratamiento_suspender'),

    # Ingreso de medicamentos
    path('residente/<int:pk>/ingreso/nuevo/', views.ingreso_crear, name='ingreso_crear'),
    path('residente/<int:pk>/ingresos/', views.ingreso_lista, name='ingreso_lista'),
    path('botiquin/ingreso/nuevo/', views.ingreso_botiquin_crear, name='ingreso_botiquin_crear'),
    path('botiquin/', views.botiquin_lista, name='botiquin_lista'),

    # Ronda por franja horaria (todo el hogar de un vistazo)
    path('ronda/', views.ronda, name='ronda'),
    path('ronda/guardar/', views.ronda_guardar, name='ronda_guardar'),

    # Hoja del día y administración
    path('residente/<int:pk>/hoja-dia/', views.hoja_dia, name='hoja_dia'),
    path('administrar/<int:prescripcion_pk>/<int:horario_pk>/', views.administracion_registrar, name='administracion_registrar'),
    path('no-administrar/<int:prescripcion_pk>/<int:horario_pk>/', views.administracion_no_registrar, name='administracion_no_registrar'),
    path('prn/<int:prescripcion_pk>/', views.administracion_prn_registrar, name='administracion_prn_registrar'),
    path('anular/<int:pk>/', views.administracion_anular, name='administracion_anular'),
]
