from django.db import models

class RouteHistory(models.Model):
    """用户路线规划历史记录"""
    user_query = models.TextField(verbose_name='用户输入')
    parsed_params = models.JSONField(verbose_name='解析参数', null=True, blank=True)
    routes_count = models.IntegerField(default=0, verbose_name='生成路线数')
    recommended_route = models.CharField(max_length=50, blank=True, verbose_name='推荐路线ID')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    total_time_s = models.FloatField(null=True, blank=True, verbose_name='总耗时(秒)')

    class Meta:
        verbose_name = '路线历史'
        verbose_name_plural = '路线历史'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user_query[:50]} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
