from django.apps import AppConfig


class SmartEngineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'smart_engine'
    verbose_name = '智能引擎（RAG/图谱/记忆/Agent）'
