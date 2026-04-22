from django.db import models


class UserProfile(models.Model):
    username = models.CharField(max_length=100, unique=True)
    avg_pace = models.FloatField(default=0, help_text="平均配速 min/km")
    preferred_terrain = models.CharField(max_length=200, blank=True, default='')
    injury_history = models.JSONField(default=list, blank=True)  # 存储受伤历史列表
    route_preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profile'

    def __str__(self):
        return self.username


class ConversationHistory(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='conversations')
    session_id = models.CharField(max_length=64, db_index=True)
    role = models.CharField(max_length=20)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'conversation_history'
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.session_id}] {self.role}: {self.content[:50]}"


class RouteRecord(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='routes')
    session_id = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=200, blank=True, default='')
    description = models.TextField(blank=True, default='')
    route_geojson = models.JSONField(default=dict, blank=True)
    distance_km = models.FloatField(default=0)
    elevation_gain = models.FloatField(default=0)
    shade_ratio = models.FloatField(default=0)
    terrain_types = models.JSONField(default=list, blank=True)
    water_stations = models.JSONField(default=list, blank=True)
    scenic_points = models.JSONField(default=list, blank=True)
    suitability_score = models.FloatField(default=0)
    ai_commentary = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'route_record'

    def __str__(self):
        return f"{self.name} ({self.distance_km}km)"
