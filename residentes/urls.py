from django.urls import path
from . import views

urlpatterns = [
    path('', views.residente_lista, name='residente_lista'),
    path('nuevo/', views.residente_crear, name='residente_crear'),
    path('<int:pk>/', views.residente_detalle, name='residente_detalle'),
    path('<int:pk>/editar/', views.residente_editar, name='residente_editar'),
    path('<int:pk>/alta/', views.residente_desactivar, name='residente_desactivar'),
    path('<int:pk>/reactivar/', views.residente_reactivar, name='residente_reactivar'),
]