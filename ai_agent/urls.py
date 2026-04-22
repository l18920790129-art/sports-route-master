from django.urls import path
from ai_agent import views

urlpatterns = [
    path('chat/', views.chat, name='chat'),
    path('routes/generate/', views.generate_routes, name='generate_routes'),
    path('layers/', views.get_layers, name='get_layers'),
    path('water-stations/', views.get_water_stations_view, name='water_stations'),
    path('scenic-points/', views.get_scenic_points_view, name='scenic_points'),
    path('shaded-roads/', views.get_shaded_roads_view, name='shaded_roads'),
    path('sea-view-roads/', views.get_sea_view_roads_view, name='sea_view_roads'),
    path('green-coverage/', views.get_green_coverage_view, name='green_coverage'),
    path('conversation/<str:session_id>/', views.get_conversation_view, name='conversation'),
    path('user/profile/', views.update_user_profile, name='update_profile'),
    path('health/', views.health_check, name='health_check'),
]
