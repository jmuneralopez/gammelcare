from django.urls import path
from . import consultas, views

urlpatterns = [
    # Catálogo
    path('buscar/', views.buscar_medicamento, name='buscar_medicamento'),
    path('crear-rapido/', views.medicamento_crear_rapido, name='medicamento_crear_rapido'),

    # Tratamientos (Prescripcion)
    path('residente/<int:pk>/tratamientos/', views.tratamiento_lista, name='tratamiento_lista'),
    path('residente/<int:pk>/tratamientos/nuevo/', views.tratamiento_crear, name='tratamiento_crear'),
    path('tratamiento/<int:pk>/', views.tratamiento_detalle, name='tratamiento_detalle'),
    path('tratamiento/<int:pk>/suspender/', views.tratamiento_suspender, name='tratamiento_suspender'),
    path('tratamiento/<int:pk>/formula/', views.tratamiento_formula_ver, name='tratamiento_formula_ver'),

    # Ingreso de medicamentos
    path('residente/<int:pk>/ingreso/nuevo/', views.ingreso_crear, name='ingreso_crear'),
    path('residente/<int:pk>/ingresos/', views.ingreso_lista, name='ingreso_lista'),
    path('botiquin/ingreso/nuevo/', views.ingreso_botiquin_crear, name='ingreso_botiquin_crear'),
    path('botiquin/', views.botiquin_lista, name='botiquin_lista'),
    path('lote/<int:pk>/descartar/', views.lote_descartar, name='lote_descartar'),
    path('prestamo/<int:pk>/repuesto/', views.prestamo_marcar_repuesto, name='prestamo_marcar_repuesto'),

    # Consulta, impresión y configuración
    path('historial/', consultas.historial_hogar, name='historial_hogar'),
    path('residente/<int:pk>/historial/', consultas.historial_residente, name='historial_residente'),
    path('residente/<int:pk>/kardex/', consultas.kardex, name='kardex'),
    path('residente/<int:pk>/hoja-tratamiento/', consultas.hoja_tratamiento, name='hoja_tratamiento'),
    path('residente/<int:pk>/devolver/', consultas.devolver, name='medicamentos_devolver'),
    path('residente/<int:pk>/acta-devolucion/', consultas.acta_devolucion, name='acta_devolucion'),
    path('residente/<int:pk>/acta-recepcion/', consultas.acta_recepcion, name='acta_recepcion'),
    path('vencimientos/', consultas.vencimientos, name='vencimientos'),
    path('configuracion/', consultas.configuracion, name='medicamentos_configuracion'),

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
