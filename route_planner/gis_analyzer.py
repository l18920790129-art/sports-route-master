"""
GIS空间分析模块
使用osmnx获取真实OSM路网数据，模拟NDVI分析、POI查询、路线生成
研究区域：厦门市环岛路（具备海景、公园、跑道等典型运动场景）
"""
import osmnx as ox
import networkx as nx
import numpy as np
import json
import random
import math
from shapely.geometry import Point, LineString, mapping
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 研究区域：厦门市环岛路附近（具备海景、公园等典型运动场景）
# ============================================================
STUDY_AREA_CENTER = (24.4434, 118.1500)  # 厦门环岛路中心点（纬度, 经度）
STUDY_AREA_NAME = "厦门市环岛路"

# 模拟的水站POI（基于真实厦门环岛路沿线位置）
SIMULATED_WATER_STATIONS = [
    {"id": "W001", "name": "椰风寨饮水站", "lat": 24.4380, "lon": 118.1420, "type": "公园饮水机"},
    {"id": "W002", "name": "白城沙滩便利店", "lat": 24.4450, "lon": 118.1510, "type": "便利店"},
    {"id": "W003", "name": "胡里山炮台补给点", "lat": 24.4390, "lon": 118.1580, "type": "景区服务站"},
    {"id": "W004", "name": "曾厝垵便利店", "lat": 24.4460, "lon": 118.1650, "type": "便利店"},
    {"id": "W005", "name": "环岛路公园饮水机", "lat": 24.4410, "lon": 118.1480, "type": "公园饮水机"},
]

# 模拟的海景观景点
SIMULATED_SEA_VIEW_POINTS = [
    {"id": "S001", "name": "灯塔观景台", "lat": 24.4350, "lon": 118.1430, "rating": 5},
    {"id": "S002", "name": "白城海滨观景平台", "lat": 24.4460, "lon": 118.1520, "rating": 4},
    {"id": "S003", "name": "胡里山海岸线", "lat": 24.4400, "lon": 118.1590, "rating": 5},
]

# 全局缓存路网（避免重复下载）
_cached_graph = None


def fetch_road_network(center_lat: float, center_lon: float, dist: int = 3000) -> nx.MultiDiGraph:
    """
    从OSM获取真实路网数据（带缓存）
    """
    global _cached_graph
    if _cached_graph is not None:
        print("[GIS] 使用缓存路网数据")
        return _cached_graph

    print(f"[GIS] 正在从OSM获取路网数据，中心点: ({center_lat}, {center_lon})，范围: {dist}m...")
    try:
        G = ox.graph_from_point(
            (center_lat, center_lon),
            dist=dist,
            network_type='walk',
            simplify=True
        )
        print(f"[GIS] 路网获取完成：{len(G.nodes)} 个节点，{len(G.edges)} 条边")
        _cached_graph = G
        return G
    except Exception as e:
        print(f"[GIS] OSM路网获取失败: {e}，使用备用模拟路网")
        return generate_mock_graph(center_lat, center_lon)


def generate_mock_graph(center_lat: float, center_lon: float) -> nx.MultiDiGraph:
    """当OSM不可用时，生成模拟路网图"""
    G = nx.MultiDiGraph()
    # 生成简单网格路网
    nodes = []
    for i in range(5):
        for j in range(5):
            nid = i * 5 + j
            lat = center_lat + (i - 2) * 0.005
            lon = center_lon + (j - 2) * 0.005
            G.add_node(nid, y=lat, x=lon)
            nodes.append(nid)

    # 添加边
    for i in range(5):
        for j in range(5):
            nid = i * 5 + j
            if j < 4:
                G.add_edge(nid, nid + 1, length=500, highway='footway')
                G.add_edge(nid + 1, nid, length=500, highway='footway')
            if i < 4:
                G.add_edge(nid, nid + 5, length=500, highway='residential')
                G.add_edge(nid + 5, nid, length=500, highway='residential')

    return G


def simulate_ndvi_analysis(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """模拟NDVI植被指数分析"""
    print("[GIS] 正在模拟NDVI植被指数分析...")

    for u, v, k, data in G.edges(data=True, keys=True):
        highway = data.get('highway', 'residential')
        if isinstance(highway, list):
            highway = highway[0]

        if highway in ['footway', 'path', 'pedestrian', 'track']:
            ndvi_base = 0.55
        elif highway in ['residential', 'living_street']:
            ndvi_base = 0.35
        elif highway in ['primary', 'secondary', 'tertiary']:
            ndvi_base = 0.20
        else:
            ndvi_base = 0.30

        u_data = G.nodes[u]
        lat = u_data.get('y', STUDY_AREA_CENTER[0])
        coastal_factor = max(0, (lat - 24.430) * 10)
        ndvi = min(0.85, max(0.05, ndvi_base + coastal_factor * 0.1 + random.gauss(0, 0.05)))

        G[u][v][k]['ndvi'] = round(ndvi, 3)
        G[u][v][k]['shade_score'] = round(ndvi * 100, 1)

    print("[GIS] NDVI分析完成")
    return G


def simulate_surface_analysis(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """模拟路面类型分析"""
    print("[GIS] 正在分析路面类型...")

    surface_map = {
        'footway': 'soft',
        'path': 'soft',
        'track': 'soft',
        'pedestrian': 'hard',
        'residential': 'hard',
        'primary': 'hard',
        'secondary': 'hard',
        'tertiary': 'hard',
        'cycleway': 'soft',
    }

    for u, v, k, data in G.edges(data=True, keys=True):
        highway = data.get('highway', 'residential')
        if isinstance(highway, list):
            highway = highway[0]
        osm_surface = data.get('surface', '')

        if osm_surface in ['asphalt', 'concrete', 'paving_stones']:
            surface = 'hard'
        elif osm_surface in ['unpaved', 'gravel', 'grass', 'dirt', 'ground']:
            surface = 'soft'
        else:
            surface = surface_map.get(highway, 'hard')

        G[u][v][k]['surface'] = surface

    print("[GIS] 路面分析完成")
    return G


def find_nearest_node(G: nx.MultiDiGraph, lat: float, lon: float) -> int:
    """找到距离给定坐标最近的路网节点"""
    return ox.nearest_nodes(G, lon, lat)


def generate_routes(G: nx.MultiDiGraph, params: dict) -> list:
    """基于用户参数生成A/B/C三条备选路线"""
    print("[GIS] 正在生成备选路线...")

    center_lat, center_lon = STUDY_AREA_CENTER
    target_distance_km = params.get('estimated_distance_km', 9.0)

    start_node = find_nearest_node(G, center_lat, center_lon)

    route_configs = [
        {
            "name": "路线A：椰风寨-灯塔环线",
            "direction_offset": (-0.010, -0.008),
            "highlight": "途经椰风寨公园，终点灯塔观景台，海景绝佳",
            "sea_view_point": SIMULATED_SEA_VIEW_POINTS[0],
        },
        {
            "name": "路线B：白城沙滩-环岛路主线",
            "direction_offset": (0.008, 0.010),
            "highlight": "沿环岛路主线跑，白城沙滩观海，树荫最多",
            "sea_view_point": SIMULATED_SEA_VIEW_POINTS[1],
        },
        {
            "name": "路线C：胡里山炮台-曾厝垵文创村",
            "direction_offset": (0.005, 0.015),
            "highlight": "途经胡里山炮台历史遗迹，曾厝垵文创村补给，路面最友好",
            "sea_view_point": SIMULATED_SEA_VIEW_POINTS[2],
        },
    ]

    routes = []
    for i, config in enumerate(route_configs):
        try:
            target_lat = center_lat + config["direction_offset"][0]
            target_lon = center_lon + config["direction_offset"][1]
            end_node = find_nearest_node(G, target_lat, target_lon)

            path_nodes = nx.shortest_path(G, start_node, end_node, weight='length')

            route_metrics = calculate_route_metrics(G, path_nodes, config, params)
            route_metrics['name'] = config['name']
            route_metrics['highlight'] = config['highlight']
            route_metrics['sea_view_point'] = config['sea_view_point']
            route_metrics['route_id'] = f"ROUTE_{chr(65+i)}"

            route_geojson = path_to_geojson(G, path_nodes)
            route_metrics['geojson'] = route_geojson

            routes.append(route_metrics)
            print(f"[GIS] {config['name']} 生成完成：{route_metrics['distance_km']:.1f}km")

        except Exception as e:
            print(f"[GIS] 路线{chr(65+i)}生成失败: {e}，使用备用方案")
            routes.append(generate_fallback_route(i, config, params))

    return routes


def calculate_route_metrics(G: nx.MultiDiGraph, path_nodes: list, config: dict, params: dict) -> dict:
    """计算路线的多维度指标"""
    total_length = 0
    total_ndvi = 0
    soft_surface_count = 0
    hard_surface_count = 0
    edge_count = 0

    for u, v in zip(path_nodes[:-1], path_nodes[1:]):
        edge_data = G.get_edge_data(u, v)
        if edge_data:
            data = list(edge_data.values())[0]
            length = data.get('length', 50)
            total_length += length
            total_ndvi += data.get('ndvi', 0.3)
            if data.get('surface') == 'soft':
                soft_surface_count += 1
            else:
                hard_surface_count += 1
            edge_count += 1

    distance_km = total_length / 1000
    avg_ndvi = total_ndvi / max(edge_count, 1)
    shade_pct = int(avg_ndvi * 100)
    elevation_gain = int(distance_km * random.uniform(8, 25))
    water_count = count_water_stations_along_route(G, path_nodes)

    soft_pct = soft_surface_count / max(edge_count, 1) * 100
    if soft_pct > 60:
        surface_desc = "塑胶跑道/土路为主（脚踝友好）"
    elif soft_pct > 30:
        surface_desc = "软硬混合路面"
    else:
        surface_desc = "铺装路面为主"

    pace_min_per_km = 6.0 + (1 - avg_ndvi) * 0.5
    estimated_time = int(distance_km * pace_min_per_km)

    return {
        "distance_km": round(distance_km, 2),
        "estimated_time_min": estimated_time,
        "shade_coverage_pct": shade_pct,
        "avg_ndvi": round(avg_ndvi, 3),
        "water_stations": water_count,
        "elevation_gain_m": elevation_gain,
        "surface_type": surface_desc,
        "soft_surface_pct": round(soft_pct, 1),
        "node_count": len(path_nodes),
    }


def count_water_stations_along_route(G: nx.MultiDiGraph, path_nodes: list, buffer_m: float = 200) -> int:
    """统计路线缓冲区（200m）内的水站数量"""
    route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in path_nodes]

    count = 0
    for station in SIMULATED_WATER_STATIONS:
        for lat, lon in route_coords:
            dist_m = math.sqrt(
                ((station['lat'] - lat) * 111000) ** 2 +
                ((station['lon'] - lon) * 111000 * math.cos(math.radians(lat))) ** 2
            )
            if dist_m < buffer_m:
                count += 1
                break
    return count


def path_to_geojson(G: nx.MultiDiGraph, path_nodes: list) -> dict:
    """将路径节点列表转换为GeoJSON LineString"""
    coords = []
    for node in path_nodes:
        node_data = G.nodes[node]
        coords.append([node_data['x'], node_data['y']])

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coords
        },
        "properties": {}
    }


def generate_fallback_route(index: int, config: dict, params: dict) -> dict:
    """当路网分析失败时，生成基于模拟数据的备用路线"""
    distance_km = params.get('estimated_distance_km', 9.0) * random.uniform(0.85, 1.15)

    fallback_data = [
        {"shade_coverage_pct": 72, "water_stations": 2, "elevation_gain_m": 85,
         "surface_type": "塑胶跑道/土路为主（脚踝友好）", "soft_surface_pct": 68.0},
        {"shade_coverage_pct": 58, "water_stations": 3, "elevation_gain_m": 120,
         "surface_type": "软硬混合路面", "soft_surface_pct": 45.0},
        {"shade_coverage_pct": 45, "water_stations": 2, "elevation_gain_m": 65,
         "surface_type": "塑胶跑道为主（脚踝友好）", "soft_surface_pct": 75.0},
    ]

    data = fallback_data[index]
    pace = 6.0
    estimated_time = int(distance_km * pace)

    return {
        "route_id": f"ROUTE_{chr(65+index)}",
        "name": config['name'],
        "distance_km": round(distance_km, 2),
        "estimated_time_min": estimated_time,
        "avg_ndvi": round(data['shade_coverage_pct'] / 100, 3),
        "highlight": config['highlight'],
        "sea_view_point": config['sea_view_point'],
        "geojson": None,
        **data
    }


def run_full_gis_analysis(params: dict) -> list:
    """执行完整的GIS分析流程，返回三条备选路线"""
    print("\n" + "="*50)
    print("开始GIS空间分析流程")
    print("="*50)

    G = fetch_road_network(STUDY_AREA_CENTER[0], STUDY_AREA_CENTER[1], dist=3500)
    G = simulate_ndvi_analysis(G)
    G = simulate_surface_analysis(G)
    routes = generate_routes(G, params)

    print("\n" + "="*50)
    print("GIS分析完成，生成了以下路线：")
    for r in routes:
        print(f"  {r['name']}: {r['distance_km']}km, 树荫{r['shade_coverage_pct']}%, 水站{r['water_stations']}个")
    print("="*50 + "\n")

    return routes
