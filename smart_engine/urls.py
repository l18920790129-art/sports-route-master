from django.urls import path
from smart_engine import views

urlpatterns = [
    # RAG 接口
    path('rag/build/', views.rag_build_index, name='rag_build'),
    path('rag/search/', views.rag_search_view, name='rag_search'),
    path('rag/stats/', views.rag_stats_view, name='rag_stats'),

    # 知识图谱接口
    path('graph/build/', views.graph_build, name='graph_build'),
    path('graph/query/', views.graph_query_view, name='graph_query'),
    path('graph/neighbors/<str:node_id>/', views.graph_neighbors_view, name='graph_neighbors'),
    path('graph/visualization/', views.graph_visualization_view, name='graph_visualization'),
    path('graph/stats/', views.graph_stats_view, name='graph_stats'),

    # 长期记忆接口
    path('memory/recall/', views.memory_recall_view, name='memory_recall'),
    path('memory/store/', views.memory_store_view, name='memory_store'),
    path('memory/stats/', views.memory_stats_view, name='memory_stats'),
    path('memory/clear/', views.memory_clear_view, name='memory_clear'),

    # Agent 接口
    path('agent/chat/', views.agent_chat_view, name='agent_chat'),
    path('agent/session/<str:session_id>/', views.agent_session_view, name='agent_session'),

    # 综合状态
    path('status/', views.smart_engine_status, name='smart_engine_status'),
]
