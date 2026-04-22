from pathlib import Path

from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_INDEX = BASE_DIR / 'frontend_dist' / 'index.html'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('ai_agent.urls')),
    path('api/smart/', include('smart_engine.urls')),
]

if FRONTEND_INDEX.exists():
    urlpatterns += [
        re_path(r'^(?!api/|admin/|static/|assets/).*$' , TemplateView.as_view(template_name='index.html')),
    ]
