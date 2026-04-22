"""
smart_engine API 视图
提供 RAG、知识图谱、长期记忆、Agent 的 HTTP 接口
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


# ─── RAG 接口 ───

@csrf_exempt
def rag_build_index(request):
    """构建/重建 RAG 索引"""
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持POST'}, status=405)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}
    force = body.get('force', False)

    from smart_engine.rag_engine import build_rag_index
    result = build_rag_index(force_rebuild=force)
    return JsonResponse(result)


@csrf_exempt
def rag_search_view(request):
    """RAG 语义检索"""
    if request.method == 'GET':
        query = request.GET.get('q', '')
        top_k = int(request.GET.get('top_k', 5))
        category = request.GET.get('category', None)
    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': '无效的请求格式'}, status=400)
        query = body.get('query', body.get('q', ''))
        top_k = body.get('top_k', 5)
        category = body.get('category', None)
    else:
        return JsonResponse({'error': '仅支持GET/POST'}, status=405)

    if not query:
        return JsonResponse({'error': '查询不能为空'}, status=400)

    from smart_engine.rag_engine import rag_search
    results = rag_search(query, top_k=top_k, category=category)
    return JsonResponse({'query': query, 'results': results, 'count': len(results)})


@csrf_exempt
def rag_stats_view(request):
    """RAG 统计信息"""
    from smart_engine.rag_engine import get_rag_stats
    return JsonResponse(get_rag_stats())


# ─── 知识图谱接口 ───

@csrf_exempt
def graph_build(request):
    """构建/重建知识图谱"""
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持POST'}, status=405)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}
    force = body.get('force', False)

    from smart_engine.knowledge_graph import build_knowledge_graph
    result = build_knowledge_graph(force_rebuild=force)
    return JsonResponse(result)


@csrf_exempt
def graph_query_view(request):
    """查询知识图谱"""
    query = request.GET.get('q', '')
    node_type = request.GET.get('type', None)
    limit = int(request.GET.get('limit', 20))

    from smart_engine.knowledge_graph import query_graph
    result = query_graph(query, node_type=node_type, limit=limit)
    return JsonResponse(result)


@csrf_exempt
def graph_neighbors_view(request, node_id):
    """获取节点邻居"""
    depth = int(request.GET.get('depth', 1))
    from smart_engine.knowledge_graph import get_node_neighbors
    result = get_node_neighbors(node_id, depth=depth)
    return JsonResponse(result)


@csrf_exempt
def graph_visualization_view(request):
    """获取图谱可视化数据"""
    limit = int(request.GET.get('limit', 200))
    from smart_engine.knowledge_graph import get_graph_visualization_data
    result = get_graph_visualization_data(limit=limit)
    return JsonResponse(result)


@csrf_exempt
def graph_stats_view(request):
    """知识图谱统计"""
    from smart_engine.knowledge_graph import get_graph_stats
    return JsonResponse(get_graph_stats())


# ─── 长期记忆接口 ───

@csrf_exempt
def memory_recall_view(request):
    """回忆用户记忆"""
    user_id = request.GET.get('user_id', 'default_user')
    memory_type = request.GET.get('type', None)
    limit = int(request.GET.get('limit', 10))

    from smart_engine.memory_engine import recall_memories
    memories = recall_memories(user_id, memory_type=memory_type, limit=limit)
    return JsonResponse({'user_id': user_id, 'memories': memories, 'count': len(memories)})


@csrf_exempt
def memory_store_view(request):
    """手动存储记忆"""
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持POST'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的请求格式'}, status=400)

    user_id = body.get('user_id', 'default_user')
    memory_type = body.get('memory_type', 'preference')
    key = body.get('key', '')
    value = body.get('value', '')
    importance = body.get('importance', 0.5)

    if not key or not value:
        return JsonResponse({'error': 'key 和 value 不能为空'}, status=400)

    from smart_engine.memory_engine import store_memory
    result = store_memory(user_id, memory_type, key, value, importance)
    return JsonResponse(result)


@csrf_exempt
def memory_stats_view(request):
    """用户记忆统计"""
    user_id = request.GET.get('user_id', 'default_user')
    from smart_engine.memory_engine import get_memory_stats
    return JsonResponse(get_memory_stats(user_id))


@csrf_exempt
def memory_clear_view(request):
    """清除用户记忆"""
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持POST'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的请求格式'}, status=400)
    user_id = body.get('user_id', 'default_user')
    from smart_engine.memory_engine import clear_user_memories
    result = clear_user_memories(user_id)
    return JsonResponse(result)


# ─── Agent 接口 ───

def _parse_intent_from_message(message):
    """从用户消息中解析路线意图（使用原始llm_agent的解析逻辑）"""
    import re
    text = (message or '').strip()

    # 提取起终点
    origin_name = ''
    dest_name = ''
    route_match = re.search(r'从\s*([^，。,；;]+?)\s*(?:到|去|跑到|骑到|走到)\s*([^，。,；;]+)', text)
    if route_match:
        origin_name = route_match.group(1).strip()
        dest_name = route_match.group(2).strip()
        # 清理终点中可能包含的后续内容
        for sep in ['途经', '途径', '经过', '路过', '然后', '再', '要求', '需要', '希望']:
            if sep in dest_name:
                dest_name = dest_name.split(sep)[0].strip()

    # 提取途经点 —— 修复：允许跨逗号/句号提取完整途径点列表
    via_names = []
    # 先尝试匹配 "途经/经过/路过" 后面的所有内容，直到遇到明确的句子终止符
    via_match = re.search(r'(?:途经|途径|经过|路过)\s*(.+?)(?:\s*(?:要求|需要|希望|大约|大概|左右|然后|再|\d+\s*(?:分钟|小时|公里|km))|$)', text)
    if via_match:
        via_raw = via_match.group(1).strip()
        # 去掉末尾可能的标点
        via_raw = re.sub(r'[，。,；;！!？?]+$', '', via_raw).strip()
        via_names = [item.strip() for item in re.split(r'[、/，,和与及\s]+', via_raw) if item.strip() and len(item.strip()) >= 2]

    # 提取运动类型
    sport_type = '跑步'
    if any(k in text for k in ['骑行', '单车', '自行车']):
        sport_type = '骑行'
    elif any(k in text for k in ['徒步', '步行', '散步']):
        sport_type = '徒步'

    # 提取时长/距离
    duration_min = 60
    target_distance_km = 10
    match_hour = re.search(r'(\d+(?:\.\d+)?)\s*小时', text)
    match_min = re.search(r'(\d+(?:\.\d+)?)\s*分钟', text)
    match_km = re.search(r'(\d+(?:\.\d+)?)\s*(?:公里|km)', text)
    if match_hour:
        duration_min = int(float(match_hour.group(1)) * 60)
    elif match_min:
        duration_min = int(float(match_min.group(1)))
    if match_km:
        target_distance_km = float(match_km.group(1))
    else:
        pace = 6.0 if sport_type == '跑步' else 3.3
        target_distance_km = round(duration_min / pace, 2)

    # 提取偏好
    need_shade = any(k in text for k in ['树荫', '林荫', '遮阴', '遮荫'])
    need_water = any(k in text for k in ['补给', '水站', '饮水', '补水'])
    need_sea_view = any(k in text for k in ['海景', '海边', '沿海', '看海'])
    avoid_hard_surface = any(k in text for k in ['脚踝', '膝盖', '膝', '跟腱', '伤病', '不适'])

    # 提取区域
    district = ''
    for d in ['思明', '湖里', '集美', '海沧', '同安', '翔安']:
        if d in text:
            district = d + '区'
            break

    return {
        'sport_type': sport_type,
        'duration_min': duration_min,
        'target_distance_km': target_distance_km,
        'origin_name': origin_name,
        'dest_name': dest_name,
        'via_names': via_names,
        'need_shade': need_shade,
        'need_water': need_water,
        'need_sea_view': need_sea_view,
        'avoid_hard_surface': avoid_hard_surface,
        'district': district,
    }


def _generate_routes_for_agent(message, intent=None):
    """为Agent对话生成路线（直接调用spatial_engine）"""
    try:
        from gis_engine.spatial_engine import build_route_with_constraints
        from ai_agent.llm_agent import generate_route_commentary

        if intent is None:
            intent = _parse_intent_from_message(message)

        constraints = {
            'target_distance_km': intent.get('target_distance_km', 10),
            'need_shade': intent.get('need_shade', False),
            'need_water': intent.get('need_water', False),
            'need_sea_view': intent.get('need_sea_view', False),
            'avoid_hard_surface': intent.get('avoid_hard_surface', False),
            'district': intent.get('district', ''),
            'start_lng': 118.089,
            'start_lat': 24.479,
            'origin_name': intent.get('origin_name', ''),
            'dest_name': intent.get('dest_name', ''),
            'via_names': intent.get('via_names', []),
        }

        logger.info(f"Agent路线生成 constraints: origin={constraints['origin_name']}, "
                     f"dest={constraints['dest_name']}, via={constraints['via_names']}")

        routes = build_route_with_constraints(constraints)

        # 为每条路线生成点评
        for route in routes:
            try:
                commentary = generate_route_commentary(route)
                route['ai_commentary'] = commentary
            except Exception as e:
                logger.warning(f"路线点评生成失败: {e}")
                route['ai_commentary'] = f"路线全程 {route.get('distance_km', 0)} 公里，" \
                                          f"预计 {route.get('duration_min', 0)} 分钟。"

        return routes
    except Exception as e:
        logger.error(f"Agent路线生成失败: {e}")
        return []


@csrf_exempt
def agent_chat_view(request):
    """Agent 智能对话 —— 融合 RAG + 图谱 + 记忆 + 路线生成"""
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持POST'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的请求格式'}, status=400)

    message = body.get('message', '').strip()
    session_id = body.get('session_id', '')
    user_id = body.get('username', body.get('user_id', 'default_user'))

    if not message:
        return JsonResponse({'error': '消息不能为空'}, status=400)

    from smart_engine.agent_engine import agent_chat
    from core.models import ConversationHistory

    # 获取历史对话
    history = []
    if session_id:
        msgs = ConversationHistory.objects.filter(session_id=session_id).order_by('created_at')
        history = [{'role': m.role, 'content': m.content} for m in msgs]

    # 调用 Agent 引擎
    result = agent_chat(user_id, session_id, message, history)

    # 如果是路线请求，直接在这里生成路线
    routes = []
    if result.get('is_route_request'):
        intent = _parse_intent_from_message(message)
        routes = _generate_routes_for_agent(message, intent)

        if routes:
            result['response'] += f"\n\n已为您生成{len(routes)}条路线方案，请在地图上查看详情。"
            # 保存路线记录
            try:
                from core.models import UserProfile, RouteRecord
                user, _ = UserProfile.objects.get_or_create(
                    username=user_id,
                    defaults={'avg_pace': 6.0, 'preferred_terrain': '公园步行道'}
                )
                for route in routes:
                    RouteRecord.objects.create(
                        user=user, session_id=session_id,
                        name=route.get('name', ''),
                        description=route.get('ai_commentary', ''),
                        route_geojson=route.get('geojson', {}),
                        distance_km=route.get('distance_km', 0),
                        elevation_gain=route.get('elevation_gain', 0),
                        shade_ratio=route.get('shade_ratio', 0),
                        terrain_types=route.get('terrain_types', []),
                        water_stations=[ws['name'] for ws in route.get('water_stations', [])],
                        scenic_points=[sp['name'] for sp in route.get('scenic_points', [])],
                        suitability_score=0.8,
                        ai_commentary=route.get('ai_commentary', ''),
                    )
            except Exception as e:
                logger.warning(f"保存路线记录失败: {e}")

    # 保存对话历史
    try:
        from core.models import UserProfile
        user, _ = UserProfile.objects.get_or_create(
            username=user_id,
            defaults={'avg_pace': 6.0, 'preferred_terrain': '公园步行道'}
        )
        ConversationHistory.objects.create(
            user=user, session_id=session_id,
            role='user', content=message,
        )
        ConversationHistory.objects.create(
            user=user, session_id=session_id,
            role='assistant', content=result.get('response', ''),
            metadata={'route_count': len(routes), 'is_route_request': result.get('is_route_request')},
        )
    except Exception as e:
        logger.warning(f"保存对话历史失败: {e}")

    # 返回结果（包含路线数据）
    result['routes'] = routes
    result['route_count'] = len(routes)
    return JsonResponse(result)


@csrf_exempt
def agent_session_view(request, session_id):
    """获取 Agent 会话信息"""
    from smart_engine.agent_engine import get_agent_session_info
    result = get_agent_session_info(session_id)
    return JsonResponse(result)


# ─── 综合状态接口 ───

@csrf_exempt
def smart_engine_status(request):
    """智能引擎综合状态"""
    from smart_engine.rag_engine import get_rag_stats
    from smart_engine.knowledge_graph import get_graph_stats
    from smart_engine.memory_engine import get_memory_stats

    user_id = request.GET.get('user_id', 'default_user')
    return JsonResponse({
        'rag': get_rag_stats(),
        'graph': get_graph_stats(),
        'memory': get_memory_stats(user_id),
        'status': 'ok',
    })
