from django.urls import path

from . import views

urlpatterns = [
    path('', views.bandeja, name='alertas_bandeja'),
    path('<int:pk>/atender/', views.atender, name='alerta_atender'),
    path('<int:pk>/descartar/', views.descartar, name='alerta_descartar'),
    path('aviso/nuevo/', views.aviso_crear, name='aviso_crear'),
    path('configuracion/', views.configuracion, name='alertas_configuracion'),
]
