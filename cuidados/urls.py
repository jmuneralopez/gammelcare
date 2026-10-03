from django.urls import path

from . import views

urlpatterns = [
    path('', views.planilla, name='cuidados_planilla'),
    path('residente/<int:pk>/', views.residente, name='cuidados_residente'),
    path('residente/<int:pk>/marcar/', views.registrar_rapido, name='cuidados_registrar_rapido'),
    path('residente/<int:pk>/registrar/', views.registrar, name='cuidados_registrar'),
    path('residente/<int:pk>/plan/', views.plan, name='cuidados_plan'),
    path('registro/<int:pk>/anular/', views.anular, name='cuidados_anular'),
    path('heridas/', views.heridas_tablero, name='cuidados_heridas'),
    path('residente/<int:pk>/herida/nueva/', views.herida_crear, name='cuidados_herida_crear'),
    path('herida/<int:pk>/', views.herida_detalle, name='cuidados_herida_detalle'),
    path('herida/<int:pk>/seguimiento/', views.seguimiento_crear, name='cuidados_seguimiento_crear'),
    path('herida/<int:pk>/cerrar/', views.herida_cerrar, name='cuidados_herida_cerrar'),
    path('seguimiento/<int:pk>/anular/', views.seguimiento_anular, name='cuidados_seguimiento_anular'),
    path('seguimiento/<int:pk>/foto/', views.foto, name='cuidados_foto'),
]
