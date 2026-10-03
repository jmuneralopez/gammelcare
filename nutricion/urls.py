from django.urls import path

from . import views

urlpatterns = [
    path('', views.planilla, name='nutricion_planilla'),
    path('residente/<int:pk>/', views.residente, name='nutricion_residente'),
    path('residente/<int:pk>/ingesta/', views.registrar_ingesta, name='nutricion_ingesta'),
    path('residente/<int:pk>/vaso/', views.vaso, name='nutricion_vaso'),
    path('residente/<int:pk>/dieta/', views.dieta, name='nutricion_dieta'),
    path('dieta/nueva/', views.tipo_dieta_crear_rapido, name='nutricion_tipo_dieta_rapido'),
    path('cocina/', views.cocina, name='nutricion_cocina'),
    path('configuracion/', views.configuracion, name='nutricion_configuracion'),
]
