from django.urls import path

from . import views

urlpatterns = [
    path('', views.bandeja, name='eventos_bandeja'),
    path('residente/<int:pk>/reportar/', views.reportar, name='eventos_reportar'),
    path('<int:pk>/', views.detalle, name='eventos_detalle'),
    path('<int:pk>/nota/', views.nota, name='eventos_nota'),
    path('<int:pk>/cerrar/', views.cerrar, name='eventos_cerrar'),
    path('vigilancia/<int:pk>/', views.vigilancia, name='eventos_vigilancia'),
    path('indicadores/', views.indicadores, name='eventos_indicadores'),
    path('configuracion/', views.configuracion, name='eventos_configuracion'),
]
