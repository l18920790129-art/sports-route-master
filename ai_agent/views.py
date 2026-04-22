import json
import uuid
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from core.models import UserProfile, ConversationHistory, RouteRecord
from gis_engine.spatial_engine import (
    build_route_with_constraints,
    get_all_layers_data,
    find_water_stations,
    find_scenic_viewpoints,
    find_shaded_roads,
    find_sea_view_roads,
    get_green_coverage_in_area,
)
from ai_agent.llm_agent import (
    parse_user_intent,
    generate_route_commentary,
    generate_multi_turn_response,
    build_knowledge_context,
    get_model_runtime_info,
)

logger = logging.getLogger(__name__)


def get_or_create_user(username='default_user'):
    user, _ = UserProfile.objects.get_or_create(
        username=username,
        defaults={'avg_pace': 6.0, 'preferred_terrain': '公园步行道'}
    )
    return user


def get_conversation_history(session_id):
    msgs = ConversationHistory.objects.filter(session_id=session_id).order_by('created_at')
    return [{'role': m.role, 'content': m.content} for m in msgs]


def save_message(user, session_id, role, content, metadata=None):
    ConversationHistory.objects.create(
        user=user,
        session_id=session_id,
        role=role,
        content=content,
        metadata=metadata or {},
    )


@csrf_exempt
def chat(request):
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持POST'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的请求格式'}, status=400)

    message = body.get('message', '').strip()
    session_id = body.get('session_id', str(uuid.uuid4()))
    username = body.get('username', 'default_user')

    if not message:
        return JsonResponse({'error': '消息不能为空'}, status=400)

    user = get_or_create_user(username)
    history = get_conversation_history(session_id)
    save_message(user, session_id, 'user', message)

    knowledge = build_knowledge_context(message)
    context = {'knowledge': knowledge} if knowledge else None
    chat_result = generate_multi_turn_response(message, history, context)

    routes = []
    intent = None
    if chat_result['is_route_request']:
        user_profile = {
            'avg_pace': user.avg_pace,
            'preferred_terrain': user.preferred_terrain,
            'injury_history': user.injury_history,
        }
        intent = parse_user_intent(message, history, user_profile)

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
        routes = build_route_with_constraints(constraints)
        for route in routes:
            commentary = generate_route_commentary(route)
            route['ai_commentary'] = commentary
            RouteRecord.objects.create(
                user=user, session_id=session_id,
                name=route['name'], description=commentary,
                route_geojson=route['geojson'],
                distance_km=route['distance_km'],
                elevation_gain=route.get('elevation_gain', 0),
                shade_ratio=route.get('shade_ratio', 0),
                terrain_types=route.get('terrain_types', []),
                water_stations=[ws['name'] for ws in route.get('water_stations', [])],
                scenic_points=[sp['name'] for sp in route.get('scenic_points', [])],
                suitability_score=0.8, ai_commentary=commentary,
            )

    response_text = chat_result['response']
    if routes:
        response_text += f"\n\n已为您生成{len(routes)}条路线方案，请在地图上查看详情。"
    save_message(user, session_id, 'assistant', response_text, {
        'intent': intent, 'route_count': len(routes),
    })

    return JsonResponse({
        'session_id': session_id,
        'response': response_text,
        'routes': routes,
        'is_route_request': chat_result['is_route_request'],
    })


@csrf_exempt
def generate_routes(request):
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持POST'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的请求格式'}, status=400)

    message = body.get('message', '').strip()
    username = body.get('username', 'default_user')
    session_id = body.get('session_id', str(uuid.uuid4()))
    if not message:
        return JsonResponse({'error': '消息不能为空'}, status=400)

    user = get_or_create_user(username)
    history = get_conversation_history(session_id)
    user_profile = {
        'avg_pace': user.avg_pace,
        'preferred_terrain': user.preferred_terrain,
        'injury_history': user.injury_history,
    }
    intent = parse_user_intent(message, history, user_profile)
    constraints = {
        'target_distance_km': intent.get('target_distance_km', 10),
        'need_shade': intent.get('need_shade', False),
        'need_water': intent.get('need_water', False),
        'need_sea_view': intent.get('need_sea_view', False),
        'avoid_hard_surface': intent.get('avoid_hard_surface', False),
        'district': intent.get('district', ''),
        'start_lng': body.get('start_lng', 118.089),
        'start_lat': body.get('start_lat', 24.479),
        'origin_name': intent.get('origin_name', ''),
        'dest_name': intent.get('dest_name', ''),
        'via_names': intent.get('via_names', []),
    }
    routes = build_route_with_constraints(constraints)
    for route in routes:
        commentary = generate_route_commentary(route)
        route['ai_commentary'] = commentary

    return JsonResponse({
        'session_id': session_id, 'intent': intent,
        'routes': routes, 'route_count': len(routes),
    })


@csrf_exempt
def get_layers(request):
    if request.method != 'GET':
        return JsonResponse({'error': '仅支持GET'}, status=405)
    layers = get_all_layers_data()
    return JsonResponse(layers)


@csrf_exempt
def get_water_stations_view(request):
    lng = float(request.GET.get('lng', 118.089))
    lat = float(request.GET.get('lat', 24.479))
    radius = float(request.GET.get('radius', 3000))
    stations = find_water_stations(lng, lat, radius)
    return JsonResponse({'water_stations': stations})


@csrf_exempt
def get_scenic_points_view(request):
    try:
        lng = float(request.GET.get('lng', 118.089))
        lat = float(request.GET.get('lat', 24.479))
        radius = float(request.GET.get('radius', 5000))
    except (ValueError, TypeError):
        return JsonResponse({'scenic_points': [], 'error': 'Invalid coordinate parameters'}, status=400)
    view_type = request.GET.get('view_type', None)
    points = find_scenic_viewpoints(lng, lat, radius, view_type)
    return JsonResponse({'scenic_points': points})


@csrf_exempt
def get_shaded_roads_view(request):
    district = request.GET.get('district', '')
    try:
        min_shade = int(request.GET.get('min_shade', 3))
    except (ValueError, TypeError):
        min_shade = 3
    roads = find_shaded_roads(district if district else None, min_shade)
    return JsonResponse({'shaded_roads': roads})


@csrf_exempt
def get_sea_view_roads_view(request):
    roads = find_sea_view_roads()
    return JsonResponse({'sea_view_roads': roads})


@csrf_exempt
def get_green_coverage_view(request):
    lng = float(request.GET.get('lng', 118.089))
    lat = float(request.GET.get('lat', 24.479))
    radius = float(request.GET.get('radius', 2000))
    coverage = get_green_coverage_in_area(lng, lat, radius)
    return JsonResponse({'green_coverage': coverage})


@csrf_exempt
def get_conversation_view(request, session_id):
    history = get_conversation_history(session_id)
    return JsonResponse({'session_id': session_id, 'messages': history})


@csrf_exempt
def update_user_profile(request):
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持POST'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的请求格式'}, status=400)
    username = body.get('username', 'default_user')
    user = get_or_create_user(username)
    if 'avg_pace' in body:
        user.avg_pace = body['avg_pace']
    if 'preferred_terrain' in body:
        user.preferred_terrain = body['preferred_terrain']
    if 'injury_history' in body:
        # injury_history 是 JSONField，直接存储列表
        injury_val = body['injury_history']
        if isinstance(injury_val, list):
            user.injury_history = injury_val
        elif isinstance(injury_val, str):
            # 兼容旧数据：如果是字符串，尝试解析为列表
            try:
                import json as _json
                parsed = _json.loads(injury_val)
                user.injury_history = parsed if isinstance(parsed, list) else [injury_val]
            except Exception:
                user.injury_history = [injury_val] if injury_val else []
        else:
            user.injury_history = []
    if 'route_preferences' in body:
        user.route_preferences = body['route_preferences']
    user.save()
    return JsonResponse({
        'username': user.username, 'avg_pace': user.avg_pace,
        'preferred_terrain': user.preferred_terrain,
        'injury_history': user.injury_history,
    })


@csrf_exempt
def health_check(request):
    from gis_engine.models import POI, RoadSegment, ScenicViewpoint, GreenCoverage

    effective_layers = get_all_layers_data()
    return JsonResponse({
        'status': 'ok',
        'data_stats': {
            'pois': POI.objects.count(),
            'roads': RoadSegment.objects.count(),
            'scenic_viewpoints': ScenicViewpoint.objects.count(),
            'green_coverage': GreenCoverage.objects.count(),
        },
        'effective_layer_stats': {
            'pois': len(effective_layers.get('pois', [])),
            'roads': len(effective_layers.get('roads', [])),
            'scenic_viewpoints': len(effective_layers.get('scenic_viewpoints', [])),
            'green_coverage': len(effective_layers.get('green_coverage', [])),
        },
        'model_info': get_model_runtime_info(),
    })
