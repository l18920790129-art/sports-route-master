"""
Django REST API 视图
"""
import json
import time
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .llm_intent_parser import parse_user_intent, generate_route_description
from .gis_analyzer import run_full_gis_analysis


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def plan_route(request):
    """
    核心API：接收用户自然语言需求，返回个性化路线方案
    POST /api/plan/
    Body: {"query": "今天下午我想进行一个90分钟的耐力跑..."}
    """
    # 处理 CORS 预检请求
    if request.method == "OPTIONS":
        response = JsonResponse({})
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    try:
        body = json.loads(request.body)
        user_query = body.get("query", "").strip()

        if not user_query:
            return JsonResponse({"error": "请输入运动需求"}, status=400)

        t_start = time.time()

        # Step 1: LLM意图解析
        print(f"\n[API] 收到用户请求: {user_query}")
        t1 = time.time()
        params = parse_user_intent(user_query)
        t_llm_parse = round(time.time() - t1, 2)
        print(f"[API] 意图解析完成，耗时 {t_llm_parse}s")

        # Step 2: GIS空间分析与路线生成
        t2 = time.time()
        routes = run_full_gis_analysis(params)
        t_gis = round(time.time() - t2, 2)
        print(f"[API] GIS分析完成，耗时 {t_gis}s，生成 {len(routes)} 条路线")

        # Step 3: LLM为每条路线生成描述
        t3 = time.time()
        for route in routes:
            route['description'] = generate_route_description(route, user_query)
        t_llm_desc = round(time.time() - t3, 2)
        print(f"[API] 路线描述生成完成，耗时 {t_llm_desc}s")

        t_total = round(time.time() - t_start, 2)

        # 推荐最优路线（综合评分）
        recommended = rank_routes(routes, params)

        # 保存历史记录（可选）
        try:
            from .models import RouteHistory
            RouteHistory.objects.create(
                user_query=user_query,
                parsed_params=params,
                routes_count=len(routes),
                recommended_route=recommended,
                total_time_s=t_total,
            )
        except Exception:
            pass  # 历史记录失败不影响主流程

        return JsonResponse({
            "success": True,
            "user_query": user_query,
            "parsed_params": params,
            "routes": routes,
            "recommended_route_id": recommended,
            "performance": {
                "total_time_s": t_total,
                "llm_parse_time_s": t_llm_parse,
                "gis_analysis_time_s": t_gis,
                "llm_description_time_s": t_llm_desc,
            }
        }, json_dumps_params={"ensure_ascii": False})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


def rank_routes(routes: list, params: dict) -> str:
    """综合评分，推荐最优路线"""
    preferred = params.get("preferred_features", [])
    constraints = params.get("health_constraints", [])

    scores = {}
    for route in routes:
        score = 0.0
        shade_w = 2.0 if "shade" in preferred else 1.0
        score += route.get("shade_coverage_pct", 0) / 100 * shade_w * 30
        water_w = 2.0 if "water" in preferred else 1.0
        score += min(route.get("water_stations", 0), 3) / 3 * water_w * 20
        ankle_w = 3.0 if "ankle" in constraints else 1.0
        score += route.get("soft_surface_pct", 0) / 100 * ankle_w * 25
        elevation_penalty = route.get("elevation_gain_m", 100) / 200
        score -= elevation_penalty * (15 if "ankle" in constraints else 5)
        if "sea_view" in preferred and route.get("sea_view_point"):
            score += 10
        scores[route["route_id"]] = round(score, 2)
        route["comprehensive_score"] = round(score, 2)

    best = max(scores, key=scores.get)
    print(f"[API] 路线综合评分: {scores}，推荐: {best}")
    return best


@require_http_methods(["GET"])
def health_check(request):
    return JsonResponse({"status": "ok", "service": "Sports Companion API", "version": "1.0.0"})
