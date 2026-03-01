from django.urls import path, include
from django.http import FileResponse
import os

def serve_frontend(request):
    """提供前端 index.html"""
    from django.conf import settings
    frontend_path = os.path.join(settings.BASE_DIR, 'frontend', 'index.html')
    return FileResponse(open(frontend_path, 'rb'), content_type='text/html')

urlpatterns = [
    path('api/', include('route_planner.urls')),
    path('', serve_frontend, name='frontend'),
]
