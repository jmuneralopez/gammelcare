from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('lista/', views.usuario_lista, name='usuario_lista'),
    path('nuevo/', views.usuario_crear, name='usuario_crear'),
    path('<int:pk>/editar/', views.usuario_editar, name='usuario_editar'),
    path('<int:pk>/toggle/', views.usuario_toggle, name='usuario_toggle'),
]