"""
知识图谱引擎
- 从 GIS 数据构建实体关系图谱
- 支持图谱查询与路径发现
- 提供可视化数据输出
"""
import logging
import math
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_graph_built = False


def _haversine(lng1, lat1, lng2, lat2):
    """计算两点间距离（米）"""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_knowledge_graph(force_rebuild: bool = False) -> Dict[str, Any]:
    """从 GIS 数据构建知识图谱"""
    global _graph_built
    from smart_engine.models import KnowledgeGraphNode, KnowledgeGraphEdge

    if _graph_built and not force_rebuild:
        return {
            'status': 'already_built',
            'nodes': KnowledgeGraphNode.objects.count(),
            'edges': KnowledgeGraphEdge.objects.count(),
        }

    nodes_created = 0
    edges_created = 0

    # ─── 创建区域节点 ───
    districts = ['思明区', '湖里区', '集美区', '海沧区', '同安区', '翔安区']
    district_nodes = {}
    for d in districts:
        node, created = KnowledgeGraphNode.objects.update_or_create(
            node_id=f"district:{d}",
            defaults={'node_type': 'district', 'name': d, 'properties': {'level': 'district'}}
        )
        district_nodes[d] = node
        if created:
            nodes_created += 1

    # ─── 创建路面类型节点 ───
    surface_types = {
        'asphalt': '沥青路面', 'concrete': '水泥路面', 'plastic_track': '塑胶跑道',
        'gravel': '碎石路', 'dirt': '土路', 'boardwalk': '木栈道',
        'brick': '砖石路', 'park_path': '公园步道',
    }
    surface_nodes = {}
    for key, name in surface_types.items():
        node, created = KnowledgeGraphNode.objects.update_or_create(
            node_id=f"surface:{key}",
            defaults={'node_type': 'surface_type', 'name': name, 'properties': {'code': key}}
        )
        surface_nodes[key] = node
        if created:
            nodes_created += 1

    # ─── 创建运动类型节点 ───
    sport_types = ['跑步', '骑行', '徒步', '步行']
    sport_nodes = {}
    for s in sport_types:
        node, created = KnowledgeGraphNode.objects.update_or_create(
            node_id=f"sport:{s}",
            defaults={'node_type': 'sport_type', 'name': s, 'properties': {}}
        )
        sport_nodes[s] = node
        if created:
            nodes_created += 1

    # ─── 从 POI 创建节点和关系 ───
    try:
        from gis_engine.models import POI
        for poi in POI.objects.all()[:500]:
            node, created = KnowledgeGraphNode.objects.update_or_create(
                node_id=f"poi:{poi.id}",
                defaults={
                    'node_type': 'poi', 'name': poi.name,
                    'lng': poi.lng, 'lat': poi.lat,
                    'properties': {'poi_type': poi.poi_type, 'address': poi.address or ''}
                }
            )
            if created:
                nodes_created += 1
            # POI -> District
            if poi.district and poi.district in district_nodes:
                _, created = KnowledgeGraphEdge.objects.update_or_create(
                    source=node, target=district_nodes[poi.district], relation='located_in',
                    defaults={'weight': 1.0}
                )
                if created:
                    edges_created += 1
    except Exception as e:
        logger.warning(f"POI图谱构建失败: {e}")

    # ─── 从路段创建节点和关系 ───
    try:
        from gis_engine.models import RoadSegment
        for road in RoadSegment.objects.all()[:300]:
            node, created = KnowledgeGraphNode.objects.update_or_create(
                node_id=f"road:{road.id}",
                defaults={
                    'node_type': 'road', 'name': road.name,
                    'properties': {
                        'surface_type': road.surface_type, 'length_m': road.length_m,
                        'shade_level': road.shade_level, 'has_sea_view': road.has_sea_view,
                    }
                }
            )
            if created:
                nodes_created += 1
            # Road -> District
            if road.district and road.district in district_nodes:
                _, created = KnowledgeGraphEdge.objects.update_or_create(
                    source=node, target=district_nodes[road.district], relation='located_in',
                    defaults={'weight': 1.0}
                )
                if created:
                    edges_created += 1
            # Road -> Surface Type
            if road.surface_type and road.surface_type in surface_nodes:
                _, created = KnowledgeGraphEdge.objects.update_or_create(
                    source=node, target=surface_nodes[road.surface_type], relation='has_surface',
                    defaults={'weight': 1.0}
                )
                if created:
                    edges_created += 1
            # Road -> Sport (适合的运动类型)
            for sport_name in ['跑步', '步行']:
                _, created = KnowledgeGraphEdge.objects.update_or_create(
                    source=node, target=sport_nodes[sport_name], relation='suitable_for',
                    defaults={'weight': 0.8}
                )
                if created:
                    edges_created += 1
            if road.surface_type in ('asphalt', 'concrete'):
                _, created = KnowledgeGraphEdge.objects.update_or_create(
                    source=node, target=sport_nodes['骑行'], relation='suitable_for',
                    defaults={'weight': 0.7}
                )
                if created:
                    edges_created += 1
    except Exception as e:
        logger.warning(f"路段图谱构建失败: {e}")

    # ─── 从景观点创建节点和关系 ───
    try:
        from gis_engine.models import ScenicViewpoint
        for sv in ScenicViewpoint.objects.all()[:200]:
            node, created = KnowledgeGraphNode.objects.update_or_create(
                node_id=f"scenic:{sv.id}",
                defaults={
                    'node_type': 'scenic', 'name': sv.name,
                    'lng': sv.lng, 'lat': sv.lat,
                    'properties': {'view_type': sv.view_type or '', 'description': sv.description or ''}
                }
            )
            if created:
                nodes_created += 1
            if sv.district and sv.district in district_nodes:
                _, created = KnowledgeGraphEdge.objects.update_or_create(
                    source=node, target=district_nodes[sv.district], relation='located_in',
                    defaults={'weight': 1.0}
                )
                if created:
                    edges_created += 1
    except Exception as e:
        logger.warning(f"景观点图谱构建失败: {e}")

    # ─── 构建空间邻近关系 ───
    try:
        all_geo_nodes = list(KnowledgeGraphNode.objects.filter(
            lng__isnull=False, lat__isnull=False
        ).exclude(node_type__in=['district', 'surface_type', 'sport_type']))

        for i, n1 in enumerate(all_geo_nodes):
            for n2 in all_geo_nodes[i + 1:]:
                dist = _haversine(n1.lng, n1.lat, n2.lng, n2.lat)
                if dist < 1000:  # 1km 内视为邻近
                    weight = max(0.1, 1.0 - dist / 1000)
                    KnowledgeGraphEdge.objects.update_or_create(
                        source=n1, target=n2, relation='near_by',
                        defaults={'weight': round(weight, 3), 'properties': {'distance_m': round(dist)}}
                    )
                    edges_created += 1
    except Exception as e:
        logger.warning(f"邻近关系构建失败: {e}")

    _graph_built = True
    total_nodes = KnowledgeGraphNode.objects.count()
    total_edges = KnowledgeGraphEdge.objects.count()
    logger.info(f"知识图谱构建完成：{total_nodes} 节点，{total_edges} 边")
    return {
        'status': 'built',
        'nodes': total_nodes,
        'edges': total_edges,
        'new_nodes': nodes_created,
        'new_edges': edges_created,
    }


def query_graph(query: str, node_type: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """查询知识图谱"""
    from smart_engine.models import KnowledgeGraphNode, KnowledgeGraphEdge

    qs = KnowledgeGraphNode.objects.all()
    if node_type:
        qs = qs.filter(node_type=node_type)
    if query:
        qs = qs.filter(name__icontains=query)

    nodes = []
    for n in qs[:limit]:
        nodes.append({
            'id': n.node_id,
            'type': n.node_type,
            'name': n.name,
            'properties': n.properties,
            'lng': n.lng,
            'lat': n.lat,
        })

    # 获取相关边
    node_ids = [n.node_id for n in qs[:limit]]
    node_objs = KnowledgeGraphNode.objects.filter(node_id__in=node_ids)
    edges_qs = KnowledgeGraphEdge.objects.filter(source__in=node_objs) | KnowledgeGraphEdge.objects.filter(target__in=node_objs)

    edges = []
    for e in edges_qs[:100]:
        edges.append({
            'source': e.source.node_id,
            'source_name': e.source.name,
            'target': e.target.node_id,
            'target_name': e.target.name,
            'relation': e.relation,
            'weight': e.weight,
        })

    return {'nodes': nodes, 'edges': edges}


def get_node_neighbors(node_id: str, depth: int = 1) -> Dict[str, Any]:
    """获取节点的邻居"""
    from smart_engine.models import KnowledgeGraphNode, KnowledgeGraphEdge

    try:
        center = KnowledgeGraphNode.objects.get(node_id=node_id)
    except KnowledgeGraphNode.DoesNotExist:
        return {'error': f'节点 {node_id} 不存在', 'nodes': [], 'edges': []}

    visited_ids = {node_id}
    all_nodes = [{
        'id': center.node_id, 'type': center.node_type,
        'name': center.name, 'properties': center.properties,
        'lng': center.lng, 'lat': center.lat,
    }]
    all_edges = []
    current_layer = [center]

    for _ in range(depth):
        next_layer = []
        for node in current_layer:
            out_edges = KnowledgeGraphEdge.objects.filter(source=node).select_related('target')
            in_edges = KnowledgeGraphEdge.objects.filter(target=node).select_related('source')
            for e in out_edges:
                all_edges.append({
                    'source': e.source.node_id, 'source_name': e.source.name,
                    'target': e.target.node_id, 'target_name': e.target.name,
                    'relation': e.relation, 'weight': e.weight,
                })
                if e.target.node_id not in visited_ids:
                    visited_ids.add(e.target.node_id)
                    all_nodes.append({
                        'id': e.target.node_id, 'type': e.target.node_type,
                        'name': e.target.name, 'properties': e.target.properties,
                        'lng': e.target.lng, 'lat': e.target.lat,
                    })
                    next_layer.append(e.target)
            for e in in_edges:
                all_edges.append({
                    'source': e.source.node_id, 'source_name': e.source.name,
                    'target': e.target.node_id, 'target_name': e.target.name,
                    'relation': e.relation, 'weight': e.weight,
                })
                if e.source.node_id not in visited_ids:
                    visited_ids.add(e.source.node_id)
                    all_nodes.append({
                        'id': e.source.node_id, 'type': e.source.node_type,
                        'name': e.source.name, 'properties': e.source.properties,
                        'lng': e.source.lng, 'lat': e.source.lat,
                    })
                    next_layer.append(e.source)
        current_layer = next_layer

    return {'center': node_id, 'nodes': all_nodes[:100], 'edges': all_edges[:200]}


def get_graph_visualization_data(limit: int = 200) -> Dict[str, Any]:
    """获取图谱可视化数据（D3.js 力导向图格式）"""
    from smart_engine.models import KnowledgeGraphNode, KnowledgeGraphEdge

    # 优先选择有连接的重要节点
    nodes_qs = KnowledgeGraphNode.objects.all()[:limit]
    node_map = {}
    nodes = []
    for n in nodes_qs:
        node_map[n.node_id] = len(nodes)
        nodes.append({
            'id': n.node_id,
            'name': n.name,
            'type': n.node_type,
            'lng': n.lng,
            'lat': n.lat,
        })

    node_objs = KnowledgeGraphNode.objects.filter(node_id__in=list(node_map.keys()))
    edges_qs = KnowledgeGraphEdge.objects.filter(
        source__in=node_objs, target__in=node_objs
    )[:500]

    links = []
    for e in edges_qs:
        if e.source.node_id in node_map and e.target.node_id in node_map:
            links.append({
                'source': e.source.node_id,
                'target': e.target.node_id,
                'relation': e.relation,
                'weight': e.weight,
            })

    return {'nodes': nodes, 'links': links}


def get_graph_stats() -> Dict[str, Any]:
    """获取图谱统计信息"""
    from smart_engine.models import KnowledgeGraphNode, KnowledgeGraphEdge
    total_nodes = KnowledgeGraphNode.objects.count()
    total_edges = KnowledgeGraphEdge.objects.count()
    by_type = {}
    for item in KnowledgeGraphNode.objects.values('node_type').distinct():
        t = item['node_type']
        by_type[t] = KnowledgeGraphNode.objects.filter(node_type=t).count()
    by_relation = {}
    for item in KnowledgeGraphEdge.objects.values('relation').distinct():
        r = item['relation']
        by_relation[r] = KnowledgeGraphEdge.objects.filter(relation=r).count()
    return {
        'total_nodes': total_nodes,
        'total_edges': total_edges,
        'nodes_by_type': by_type,
        'edges_by_relation': by_relation,
        'graph_built': _graph_built,
    }
