from django.urls import path
from . import views

urlpatterns = [
    path('', views.hogar_lista, name='hogar_lista'),
    path('nuevo/', views.hogar_crear, name='hogar_crear'),
    path('<int:pk>/editar/', views.hogar_editar, name='hogar_editar'),
    path('<int:pk>/toggle/', views.hogar_toggle, name='hogar_toggle'),
]