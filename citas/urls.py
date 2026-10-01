from django.urls import path

from . import views

urlpatterns = [
    path('', views.agenda, name='citas_agenda'),
    path('residente/<int:pk>/', views.residente_citas, name='citas_residente'),
    path('residente/<int:pk>/nueva/', views.cita_crear, name='cita_crear'),
    path('<int:pk>/', views.cita_detalle, name='cita_detalle'),
    path('<int:pk>/corregir/', views.cita_editar, name='cita_editar'),
    path('<int:pk>/cerrar/', views.cita_cerrar, name='cita_cerrar'),
    path('<int:pk>/cancelar/', views.cita_cancelar, name='cita_cancelar'),
    path('<int:pk>/reprogramar/', views.cita_reprogramar, name='cita_reprogramar'),
    path('<int:pk>/soporte/', views.cita_soporte_ver, name='cita_soporte_ver'),
]
