from django.urls import path
from . import views

urlpatterns = [
    path('', views.auditoria_lista, name='auditoria_lista'),
]
