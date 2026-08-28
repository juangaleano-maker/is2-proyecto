from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('menu/', views.menu, name='menu'),
]
