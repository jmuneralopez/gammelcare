from django.urls import path
from . import views

urlpatterns = [
    path('residente/<int:pk>/nueva/', views.nota_crear, name='nota_crear'),
    path('<int:pk>/', views.nota_detalle, name='nota_detalle'),
    path('<int:pk>/aclaratoria/', views.aclaratoria_crear, name='aclaratoria_crear'),
]