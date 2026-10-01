from django.urls import path

from . import views

urlpatterns = [
    path('', views.bandeja, name='examenes_bandeja'),
    path('residente/<int:pk>/', views.residente_examenes, name='examenes_residente'),
    path('residente/<int:pk>/nuevo/', views.examen_crear, name='examen_crear'),
    path('residente/<int:pk>/tendencias/', views.tendencias, name='examenes_tendencias'),
    path('<int:pk>/', views.examen_detalle, name='examen_detalle'),
    path('<int:pk>/editar/', views.examen_editar, name='examen_editar'),
    path('<int:pk>/resultado/', views.examen_resultado, name='examen_resultado'),
    path('<int:pk>/adenda/', views.examen_adenda, name='examen_adenda'),
    path('<int:pk>/revisar/', views.examen_revisar, name='examen_revisar'),
    path('<int:pk>/cancelar/', views.examen_cancelar, name='examen_cancelar'),
    path('valor/<int:pk>/corregir/', views.valor_corregir, name='valor_corregir'),
    path('archivo/<int:pk>/', views.archivo_ver, name='archivo_ver'),
    path('analito/nuevo/', views.analito_crear_rapido, name='analito_crear_rapido'),
]
