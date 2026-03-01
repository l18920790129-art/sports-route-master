from django.urls import path
from . import views

urlpatterns = [
    path('plan/', views.plan_route, name='plan_route'),
    path('health/', views.health_check, name='health_check'),
]
