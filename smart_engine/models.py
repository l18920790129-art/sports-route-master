"""
smart_engine 数据模型
- KnowledgeDocument: RAG 知识文档（含向量嵌入）
- KnowledgeGraphNode / KnowledgeGraphEdge: 知识图谱节点与边
- LongTermMemory: 长期记忆条目
- AgentSession: Agent 会话状态
"""
from django.db import models


class KnowledgeDocument(models.Model):
    """RAG 知识文档：存储文本片段及其向量嵌入"""
    doc_id = models.CharField(max_length=128, unique=True, db_index=True)
    category = models.CharField(max_length=64, db_index=True,
                                help_text="分类：poi/road/scenic/green/sports_medicine/xiamen_knowledge")
    title = models.CharField(max_length=256)
    content = models.TextField(help_text="文本内容")
    embedding = models.JSONField(default=list, help_text="向量嵌入（list of float）")
    source_type = models.CharField(max_length=64, default='database',
                                   help_text="来源：database/manual/crawled")
    source_id = models.CharField(max_length=128, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_document'
        ordering = ['-updated_at']

    def __str__(self):
        return f"[{self.category}] {self.title}"


class KnowledgeGraphNode(models.Model):
    """知识图谱节点"""
    node_id = models.CharField(max_length=128, unique=True, db_index=True)
    node_type = models.CharField(max_length=64, db_index=True,
                                 help_text="类型：poi/road/scenic/green/district/surface_type/sport_type")
    name = models.CharField(max_length=256)
    properties = models.JSONField(default=dict, blank=True)
    lng = models.FloatField(null=True, blank=True)
    lat = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_graph_node'
        ordering = ['node_type', 'name']

    def __str__(self):
        return f"[{self.node_type}] {self.name}"


class KnowledgeGraphEdge(models.Model):
    """知识图谱边（关系）"""
    source = models.ForeignKey(KnowledgeGraphNode, on_delete=models.CASCADE, related_name='outgoing_edges')
    target = models.ForeignKey(KnowledgeGraphNode, on_delete=models.CASCADE, related_name='incoming_edges')
    relation = models.CharField(max_length=128, db_index=True,
                                help_text="关系类型：located_in/has_surface/near_by/connects_to/provides/overlooks")
    weight = models.FloatField(default=1.0)
    properties = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_graph_edge'
        unique_together = ('source', 'target', 'relation')

    def __str__(self):
        return f"{self.source.name} --[{self.relation}]--> {self.target.name}"


class LongTermMemory(models.Model):
    """长期记忆：跨会话持久化用户偏好、习惯、历史摘要"""
    MEMORY_TYPES = [
        ('preference', '用户偏好'),
        ('habit', '运动习惯'),
        ('route_history', '路线历史'),
        ('feedback', '用户反馈'),
        ('context', '上下文摘要'),
    ]
    user_id = models.CharField(max_length=100, db_index=True)
    memory_type = models.CharField(max_length=32, choices=MEMORY_TYPES, db_index=True)
    key = models.CharField(max_length=256, help_text="记忆键，如 preferred_distance / last_route")
    value = models.TextField(help_text="记忆值")
    importance = models.FloatField(default=0.5, help_text="重要性权重 0-1")
    access_count = models.IntegerField(default=0)
    last_accessed = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'long_term_memory'
        ordering = ['-importance', '-last_accessed']
        unique_together = ('user_id', 'memory_type', 'key')

    def __str__(self):
        return f"[{self.user_id}] {self.memory_type}: {self.key}"


class AgentSession(models.Model):
    """Agent 会话状态：跟踪多轮对话中的需求演变"""
    session_id = models.CharField(max_length=64, unique=True, db_index=True)
    user_id = models.CharField(max_length=100, db_index=True)
    current_intent = models.JSONField(default=dict, blank=True,
                                      help_text="当前累积的用户意图")
    clarification_history = models.JSONField(default=list, blank=True,
                                             help_text="追问与澄清历史")
    state = models.CharField(max_length=32, default='idle',
                             help_text="会话状态：idle/gathering/planning/refining/completed")
    turn_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_session'

    def __str__(self):
        return f"Session {self.session_id} [{self.state}]"
