from django.urls import path
from . import views

urlpatterns = [
    path('', views.residente_lista, name='residente_lista'),
    path('nuevo/', views.residente_crear, name='residente_crear'),
    path('<int:pk>/', views.residente_detalle, name='residente_detalle'),
    path('<int:pk>/editar/', views.residente_editar, name='residente_editar'),
    path('<int:pk>/alta/', views.residente_desactivar, name='residente_desactivar'),
    path('<int:pk>/reactivar/', views.residente_reactivar, name='residente_reactivar'),
    path('<int:pk>/diagnostico/nuevo/', views.diagnostico_agregar, name='diagnostico_agregar'),
    path('<int:pk>/diagnostico/<int:dpk>/remover/', views.diagnostico_desactivar, name='diagnostico_desactivar'),
    path('<int:pk>/pdf/', views.residente_exportar_pdf, name='residente_pdf'),
]