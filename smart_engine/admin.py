from django.contrib import admin
from smart_engine.models import (
    KnowledgeDocument, KnowledgeGraphNode, KnowledgeGraphEdge,
    LongTermMemory, AgentSession,
)

@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ('doc_id', 'category', 'title', 'source_type', 'updated_at')
    list_filter = ('category', 'source_type')
    search_fields = ('title', 'content')

@admin.register(KnowledgeGraphNode)
class KnowledgeGraphNodeAdmin(admin.ModelAdmin):
    list_display = ('node_id', 'node_type', 'name', 'lng', 'lat')
    list_filter = ('node_type',)
    search_fields = ('name',)

@admin.register(KnowledgeGraphEdge)
class KnowledgeGraphEdgeAdmin(admin.ModelAdmin):
    list_display = ('source', 'relation', 'target', 'weight')
    list_filter = ('relation',)

@admin.register(LongTermMemory)
class LongTermMemoryAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'memory_type', 'key', 'value', 'importance', 'access_count')
    list_filter = ('memory_type',)
    search_fields = ('user_id', 'key')

@admin.register(AgentSession)
class AgentSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'user_id', 'state', 'turn_count', 'updated_at')
    list_filter = ('state',)
