from django.urls import path

from . import views

urlpatterns = [
    path('', views.tablero, name='valoracion_tablero'),
    path('residente/<int:pk>/', views.residente, name='valoracion_residente'),
    path('residente/<int:pk>/aplicar/<slug:codigo>/', views.aplicar, name='valoracion_aplicar'),
    path('<int:pk>/', views.detalle, name='valoracion_detalle'),
    path('<int:pk>/anular/', views.anular, name='valoracion_anular'),
    path('configuracion/', views.configuracion, name='valoracion_configuracion'),
]
