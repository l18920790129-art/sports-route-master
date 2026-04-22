"""
高德地图API数据采集模块
通过高德Web服务API获取厦门市真实POI数据并入库
"""
import os
import requests
import time
import logging
import math
from django.conf import settings

logger = logging.getLogger(__name__)

AMAP_SERVER_KEY = os.getenv('AMAP_SERVER_KEY', 'REPLACE_WITH_AMAP_SERVER_KEY')
BASE_URL = 'https://restapi.amap.com/v3'

XIAMEN_CITY_CODE = '350200'
XIAMEN_DISTRICTS = ['思明区', '湖里区', '集美区', '海沧区', '同安区', '翔安区']

POI_TYPE_MAP = {
    'water_station': [
        ('060101', '便利店'),
        ('060400', '超市'),
        ('110300', '公园附属设施'),
    ],
    'scenic_point': [
        ('110200', '风景名胜'),
        ('110202', '海滨浴场'),
        ('110204', '自然景观'),
    ],
    'park': [
        ('110101', '公园'),
        ('110102', '城市广场'),
    ],
    'sports_facility': [
        ('080100', '体育场馆'),
        ('080600', '运动场所'),
        ('080102', '综合体育馆'),
    ],
    'toilet': [
        ('200300', '公共厕所'),
    ],
}


def amap_request(endpoint, params):
    params['key'] = AMAP_SERVER_KEY
    params['output'] = 'json'
    url = f"{BASE_URL}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get('status') == '1':
            return data
        logger.warning(f"AMap API error: {data.get('info')} for {endpoint}")
        return None
    except Exception as e:
        logger.error(f"AMap request failed: {e}")
        return None


def fetch_pois_by_type(type_code, city='厦门', page=1, page_size=25):
    params = {
        'types': type_code,
        'city': city,
        'citylimit': 'true',
        'page': page,
        'offset': page_size,
        'extensions': 'all',
    }
    return amap_request('place/text', params)


def fetch_all_pois_for_type(type_code, poi_category, type_name):
    all_pois = []
    page = 1
    while True:
        data = fetch_pois_by_type(type_code, page=page)
        if not data or not data.get('pois'):
            break
        pois = data['pois']
        for poi in pois:
            location = poi.get('location', '')
            if not location:
                continue
            lng, lat = location.split(',')
            all_pois.append({
                'amap_id': poi.get('id', ''),
                'name': poi.get('name', ''),
                'poi_type': poi_category,
                'amap_type_code': poi.get('typecode', ''),
                'lng': float(lng),
                'lat': float(lat),
                'address': poi.get('address', '') if isinstance(poi.get('address'), str) else '',
                'district': poi.get('adname', ''),
                'tel': poi.get('tel', '') if isinstance(poi.get('tel'), str) else '',
                'raw_data': poi,
            })
        total = int(data.get('count', 0))
        if page * 25 >= total or page >= 10:
            break
        page += 1
        time.sleep(0.3)
    logger.info(f"Fetched {len(all_pois)} POIs for {type_name} ({type_code})")
    return all_pois


def collect_all_pois():
    from gis_engine.models import POI
    total_count = 0
    for category, type_list in POI_TYPE_MAP.items():
        for type_code, type_name in type_list:
            pois = fetch_all_pois_for_type(type_code, category, type_name)
            for poi_data in pois:
                POI.objects.update_or_create(
                    amap_id=poi_data['amap_id'],
                    defaults=poi_data
                )
                total_count += 1
            time.sleep(0.5)
    logger.info(f"Total POIs collected: {total_count}")
    return total_count


def fetch_walking_route(origin_lng, origin_lat, dest_lng, dest_lat):
    params = {
        'origin': f"{origin_lng},{origin_lat}",
        'destination': f"{dest_lng},{dest_lat}",
    }
    return amap_request('direction/walking', params)


def fetch_road_info(lng, lat, radius=1000):
    params = {
        'location': f"{lng},{lat}",
        'radius': radius,
        'types': '190301|190302|190303|190304|190305',
        'extensions': 'all',
        'offset': 25,
    }
    return amap_request('place/around', params)


def geocode_address(address):
    params = {
        'address': address,
        'city': '厦门',
    }
    return amap_request('geocode/geo', params)


def reverse_geocode(lng, lat):
    params = {
        'location': f"{lng},{lat}",
        'extensions': 'all',
        'radius': 200,
    }
    return amap_request('geocode/regeo', params)


def fetch_scenic_viewpoints():
    from gis_engine.models import ScenicViewpoint
    scenic_keywords = [
        ('海景', 'sea_view'),
        ('观景台', 'sea_view'),
        ('灯塔', 'lighthouse'),
        ('日落', 'sunset'),
    ]
    count = 0
    for keyword, view_type in scenic_keywords:
        params = {
            'keywords': keyword,
            'city': '厦门',
            'citylimit': 'true',
            'offset': 25,
            'page': 1,
            'extensions': 'all',
        }
        data = amap_request('place/text', params)
        if not data or not data.get('pois'):
            continue
        for poi in data['pois']:
            location = poi.get('location', '')
            if not location:
                continue
            lng, lat = location.split(',')
            ScenicViewpoint.objects.update_or_create(
                name=poi.get('name', ''),
                view_type=view_type,
                defaults={
                    'lng': float(lng),
                    'lat': float(lat),
                    'description': poi.get('address', '') if isinstance(poi.get('address'), str) else '',
                    'district': poi.get('adname', ''),
                }
            )
            count += 1
        time.sleep(0.5)
    logger.info(f"Scenic viewpoints collected: {count}")
    return count


def generate_green_coverage_grid():
    from gis_engine.models import GreenCoverage
    bounds = settings.XIAMEN_BOUNDS
    step = 0.008
    count = 0
    lat = bounds['south']
    grid_idx = 0
    while lat <= bounds['north']:
        lng = bounds['west']
        while lng <= bounds['east']:
            grid_idx += 1
            params = {
                'location': f"{lng:.6f},{lat:.6f}",
                'radius': 500,
                'types': '110101|110102|110300',
                'offset': 5,
            }
            data = amap_request('place/around', params)
            park_count = 0
            if data and data.get('pois'):
                park_count = len(data['pois'])
            ndvi = min(0.2 + park_count * 0.15, 0.85) if park_count > 0 else 0.1
            shade = min(park_count, 5)
            regeo = reverse_geocode(lng, lat)
            district = ''
            if regeo and regeo.get('regeocode'):
                addr_comp = regeo['regeocode'].get('addressComponent', {})
                district = addr_comp.get('district', '')
            GreenCoverage.objects.update_or_create(
                grid_id=f"G{grid_idx:05d}",
                defaults={
                    'center_lng': round(lng, 6),
                    'center_lat': round(lat, 6),
                    'ndvi_value': round(ndvi, 3),
                    'shade_level': shade,
                    'district': district,
                }
            )
            count += 1
            lng += step
            time.sleep(0.2)
        lat += step
    logger.info(f"Green coverage grids generated: {count}")
    return count


def collect_road_segments():
    from gis_engine.models import RoadSegment
    running_locations = [
        {'name': '环岛路', 'lng': 118.145, 'lat': 24.437, 'surface': 'asphalt', 'sea_view': True, 'shade': 2},
        {'name': '五缘湾湿地公园步道', 'lng': 118.178, 'lat': 24.516, 'surface': 'park_path', 'sea_view': True, 'shade': 4},
        {'name': '仙岳山步道', 'lng': 118.108, 'lat': 24.494, 'surface': 'mountain_trail', 'sea_view': False, 'shade': 4},
        {'name': '狐尾山步道', 'lng': 118.087, 'lat': 24.486, 'surface': 'mountain_trail', 'sea_view': True, 'shade': 3},
        {'name': '白鹭洲公园步道', 'lng': 118.089, 'lat': 24.462, 'surface': 'park_path', 'sea_view': False, 'shade': 4},
        {'name': '集美大桥绿道', 'lng': 118.097, 'lat': 24.566, 'surface': 'asphalt', 'sea_view': True, 'shade': 1},
        {'name': '杏林湾环湾绿道', 'lng': 118.058, 'lat': 24.584, 'surface': 'park_path', 'sea_view': True, 'shade': 3},
        {'name': '海沧大道绿道', 'lng': 118.032, 'lat': 24.484, 'surface': 'asphalt', 'sea_view': True, 'shade': 2},
        {'name': '同安湾滨海步道', 'lng': 118.178, 'lat': 24.596, 'surface': 'boardwalk', 'sea_view': True, 'shade': 1},
        {'name': '翔安大道绿道', 'lng': 118.258, 'lat': 24.618, 'surface': 'asphalt', 'sea_view': False, 'shade': 2},
        {'name': '厦门大学周边步道', 'lng': 118.098, 'lat': 24.438, 'surface': 'park_path', 'sea_view': True, 'shade': 5},
        {'name': '万石植物园步道', 'lng': 118.108, 'lat': 24.453, 'surface': 'mountain_trail', 'sea_view': False, 'shade': 5},
        {'name': '海沧湾公园跑道', 'lng': 118.023, 'lat': 24.472, 'surface': 'plastic_track', 'sea_view': True, 'shade': 2},
        {'name': '五缘湾跑步道', 'lng': 118.185, 'lat': 24.520, 'surface': 'plastic_track', 'sea_view': True, 'shade': 2},
        {'name': '集美学村步道', 'lng': 118.098, 'lat': 24.553, 'surface': 'park_path', 'sea_view': True, 'shade': 3},
    ]

    count = 0
    for loc in running_locations:
        walk_data = fetch_walking_route(
            loc['lng'], loc['lat'],
            loc['lng'] + 0.008, loc['lat'] + 0.005
        )
        path_coords = []
        total_distance = 0
        if walk_data and walk_data.get('route'):
            paths = walk_data['route'].get('paths', [])
            if paths:
                total_distance = float(paths[0].get('distance', 0))
                for step in paths[0].get('steps', []):
                    polyline = step.get('polyline', '')
                    for point in polyline.split(';'):
                        if ',' in point:
                            plng, plat = point.split(',')
                            path_coords.append([float(plng), float(plat)])

        if not path_coords:
            path_coords = [[loc['lng'], loc['lat']], [loc['lng'] + 0.008, loc['lat'] + 0.005]]
            total_distance = 1000

        regeo = reverse_geocode(loc['lng'], loc['lat'])
        district = ''
        if regeo and regeo.get('regeocode'):
            addr_comp = regeo['regeocode'].get('addressComponent', {})
            district = addr_comp.get('district', '')

        geojson = {
            'type': 'LineString',
            'coordinates': path_coords
        }

        RoadSegment.objects.update_or_create(
            name=loc['name'],
            defaults={
                'surface_type': loc['surface'],
                'path_geojson': geojson,
                'district': district,
                'length_m': total_distance,
                'avg_slope': 0,
                'shade_level': loc['shade'],
                'has_sea_view': loc['sea_view'],
            }
        )
        count += 1
        time.sleep(0.5)

    logger.info(f"Road segments collected: {count}")
    return count


def run_full_collection():
    logger.info("Starting full data collection from AMap API...")
    results = {}
    results['pois'] = collect_all_pois()
    results['scenic'] = fetch_scenic_viewpoints()
    results['roads'] = collect_road_segments()
    logger.info(f"Collection complete: {results}")
    return results
