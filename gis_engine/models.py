from django.db import models


class POI(models.Model):
    TYPE_CHOICES = [
        ('water_station', '饮水站/便利店'),
        ('scenic_point', '观景点'),
        ('park', '公园'),
        ('sports_facility', '运动设施'),
        ('toilet', '公共厠所'),
        ('parking', '停车场'),
    ]

    amap_id = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    poi_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    amap_type_code = models.CharField(max_length=100, blank=True)
    lng = models.FloatField()
    lat = models.FloatField()
    address = models.CharField(max_length=500, blank=True)
    district = models.CharField(max_length=100, blank=True)
    tel = models.CharField(max_length=100, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gis_poi'
        indexes = [
            models.Index(fields=['poi_type']),
            models.Index(fields=['district']),
            models.Index(fields=['lng', 'lat']),
        ]

    def __str__(self):
        return f"{self.name} ({self.poi_type})"


class RoadSegment(models.Model):
    SURFACE_CHOICES = [
        ('plastic_track', '塑胶跑道'),
        ('dirt_trail', '土路'),
        ('asphalt', '汥青公路'),
        ('concrete', '水泥路'),
        ('mountain_trail', '山路'),
        ('park_path', '公园步行道'),
        ('boardwalk', '木栈道'),
        ('beach', '沙滩'),
    ]

    name = models.CharField(max_length=200)
    surface_type = models.CharField(max_length=50, choices=SURFACE_CHOICES)
    path_geojson = models.JSONField()
    district = models.CharField(max_length=100, blank=True)
    length_m = models.FloatField(default=0)
    avg_slope = models.FloatField(default=0, help_text="平均坡度百分比")
    shade_level = models.IntegerField(default=0, help_text="遮荫等级 0-5")
    has_sea_view = models.BooleanField(default=False)
    elevation_data = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gis_road_segment'
        indexes = [
            models.Index(fields=['surface_type']),
            models.Index(fields=['district']),
        ]

    def __str__(self):
        return f"{self.name} ({self.surface_type})"


class GreenCoverage(models.Model):
    grid_id = models.CharField(max_length=20, unique=True)
    center_lng = models.FloatField()
    center_lat = models.FloatField()
    ndvi_value = models.FloatField(default=0, help_text="NDVI植被指数 -1到1")
    shade_level = models.IntegerField(default=0, help_text="遮荫等级 0-5")
    district = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gis_green_coverage'
        indexes = [
            models.Index(fields=['center_lng', 'center_lat']),
        ]


class ScenicViewpoint(models.Model):
    VIEW_CHOICES = [
        ('sea_view', '海景'),
        ('mountain_view', '山景'),
        ('city_view', '城市景观'),
        ('sunset', '日落观景'),
        ('lighthouse', '灯塔'),
    ]

    name = models.CharField(max_length=200)
    view_type = models.CharField(max_length=50, choices=VIEW_CHOICES)
    lng = models.FloatField()
    lat = models.FloatField()
    description = models.TextField(blank=True)
    view_angle_start = models.FloatField(default=0, help_text="视线起始角度")
    view_angle_end = models.FloatField(default=360, help_text="视线结束角度")
    elevation = models.FloatField(default=0)
    district = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gis_scenic_viewpoint'

    def __str__(self):
        return f"{self.name} ({self.view_type})"
