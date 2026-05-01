from django.urls import path
from . import views

urlpatterns = [
    path('', views.atencion_lista, name='atencion_lista'),
    path('residente/<int:pk>/nueva/', views.nota_crear, name='nota_crear'),
    path('residente/<int:pk>/calendario/', views.notas_calendario, name='notas_calendario'),
    path('residente/<int:pk>/calendario/data/', views.notas_calendario_data, name='notas_calendario_data'),
    path('<int:pk>/', views.nota_detalle, name='nota_detalle'),
    path('<int:pk>/aclaratoria/', views.aclaratoria_crear, name='aclaratoria_crear'),
]