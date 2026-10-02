from django.urls import path

from . import views

urlpatterns = [
    path('', views.tablero, name='plan_tablero'),
    path('residente/<int:pk>/', views.residente, name='plan_residente'),
    path('residente/<int:pk>/nuevo/', views.crear_borrador, name='plan_crear'),
    path('<int:pk>/', views.detalle, name='plan_detalle'),
    path('<int:pk>/datos/', views.editar, name='plan_editar'),
    path('<int:pk>/activar/', views.activar, name='plan_activar'),
    path('<int:pk>/descartar/', views.descartar_borrador, name='plan_descartar'),
    path('<int:pk>/objetivo/nuevo/', views.objetivo_crear, name='plan_objetivo_crear'),
    path('objetivo/<int:pk>/corregir/', views.objetivo_editar, name='plan_objetivo_editar'),
    path('objetivo/<int:pk>/quitar/', views.objetivo_quitar, name='plan_objetivo_quitar'),
    path('objetivo/<int:pk>/seguimiento/', views.seguimiento, name='plan_seguimiento'),
]
