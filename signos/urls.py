from django.urls import path

from . import views

urlpatterns = [
    path('', views.tablero, name='signos_tablero'),
    path('residente/<int:pk>/', views.residente, name='signos_residente'),
    path('residente/<int:pk>/registrar/', views.control_crear, name='signos_control_crear'),
    path('residente/<int:pk>/liquidos/', views.liquidos_crear, name='signos_liquidos_crear'),
    path('residente/<int:pk>/rango/', views.rango_residente, name='signos_rango_residente'),
    path('control/<int:pk>/anular/', views.control_anular, name='signos_control_anular'),
    path('liquidos/<int:pk>/anular/', views.liquidos_anular, name='signos_liquidos_anular'),
    path('rango/<int:pk>/quitar/', views.rango_residente_quitar, name='signos_rango_quitar'),
    path('rangos-del-hogar/', views.rangos_hogar, name='signos_rangos_hogar'),
]
