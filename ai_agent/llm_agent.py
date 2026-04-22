"""
DeepSeek AI Agent
负责理解用户自然语言需求、识别是否需要生成路线，并输出更稳定的路线点评。
默认优先使用 deepseek-reasoner，以获得更强的推理效果。
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是厦门市专业运动路线规划系统的意图解析模块。你的唯一任务是将用户的自然语言转化为结构化JSON参数。

严格规则：
- 用户说“从A到B”或“从A跑到B”，必须提取 origin_name 和 dest_name
- 用户说“途经/经过/路过某地”，必须将地点加入 via_names 数组
- 如果用户没有明确起终点，origin_name 和 dest_name 设为空字符串
- 如果用户提到脚踝/膝盖不适，设置 avoid_hard_surface=true
- 根据运动时长和配速估算 target_distance_km
- 所有路线必须在厦门市范围内
- 不要添加解释文字，只输出 JSON

输出格式：
{
  "sport_type": "跑步",
  "duration_min": 90,
  "target_distance_km": 15,
  "origin_name": "厦门大学北门",
  "dest_name": "厦门大学南门",
  "via_names": ["将军祠"],
  "need_shade": true,
  "need_water": true,
  "need_sea_view": true,
  "avoid_hard_surface": false,
  "preferred_surfaces": ["park_path", "plastic_track"],
  "district": "",
  "injury_notes": "",
  "pace_min_per_km": 6.0,
  "special_requirements": [],
  "analysis_summary": "用户需要从厦门大学北门跑到南门，途经将军祠"
}"""

COACH_SYSTEM_PROMPT = """你是「运动路线大师」——厦门市高阶运动路线规划AI教练。

你的任务：
1. 精准理解用户的起点、终点、途经点、时长、强度、伤病与偏好。
2. 对用户给出的运动需求做专业路线判断。
3. 当用户信息已经足够时，直接给出简洁、专业、有判断力的分析，并在结尾加上 [ROUTE_REQUEST]。
4. 当用户信息不足时，明确指出缺少的关键信息，尽量一两句话说明。

风格要求：
- 直接、专业、像资深教练，不要客套。
- 不要空话，不要套话。
- 优先给出可执行建议。
- 控制在 220 字以内。
- 不使用 emoji。
"""


_def_base_url = os.getenv('DEEPSEEK_BASE_URL') or getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
_def_api_key = os.getenv('DEEPSEEK_API_KEY') or getattr(settings, 'DEEPSEEK_API_KEY', '')
REASONING_MODEL = os.getenv('DEEPSEEK_REASONING_MODEL') or getattr(settings, 'DEEPSEEK_REASONING_MODEL', 'deepseek-reasoner')
CHAT_MODEL = os.getenv('DEEPSEEK_CHAT_MODEL') or getattr(settings, 'DEEPSEEK_CHAT_MODEL', 'deepseek-chat')

# 设置较短的超时，确保 API 不可用时能快速 fallback 到规则引擎
_API_TIMEOUT = float(os.getenv('DEEPSEEK_TIMEOUT', '8'))
client = OpenAI(api_key=_def_api_key, base_url=_def_base_url, timeout=_API_TIMEOUT) if _def_api_key else None


def _safe_history(conversation_history: Optional[List[Dict[str, Any]]] = None, limit: int = 8) -> List[Dict[str, str]]:
    if not conversation_history:
        return []
    cleaned: List[Dict[str, str]] = []
    for msg in conversation_history[-limit:]:
        role = (msg or {}).get('role', 'user')
        if role not in {'system', 'user', 'assistant'}:
            role = 'user'
        content = str((msg or {}).get('content', '')).strip()
        if content:
            cleaned.append({'role': role, 'content': content})
    return cleaned


def _message_text(choice_message: Any) -> str:
    if choice_message is None:
        return ''
    content = getattr(choice_message, 'content', '')
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                chunks.append(item.get('text', ''))
        return ''.join(chunks).strip()
    return str(content).strip()


def _looks_like_route_request(text: str) -> bool:
    if not text:
        return False
    keywords = [
        '路线', '跑步', '慢跑', '骑行', '徒步', '步行', '通勤', '配速', '公里', '分钟', '小时',
        '从', '到', '途经', '经过', '路过', '海景', '树荫', '林荫', '补给', '水站', '规划'
    ]
    return any(kw in text for kw in keywords)


def _extract_duration_minutes(text: str) -> int:
    match_hour = re.search(r'(\d+(?:\.\d+)?)\s*小时', text)
    if match_hour:
        return int(float(match_hour.group(1)) * 60)

    match_min = re.search(r'(\d+(?:\.\d+)?)\s*分钟', text)
    if match_min:
        return int(float(match_min.group(1)))

    return 60


def _heuristic_intent(user_message: str, user_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    text = (user_message or '').strip()
    profile = user_profile or {}
    duration_min = _extract_duration_minutes(text)
    sport_type = '骑行' if any(k in text for k in ['骑行', '单车', '自行车']) else '跑步'
    pace = float(profile.get('avg_pace', 6.0) or 6.0)

    # 优先从消息中提取明确的距离数字（如"5公里""10km""15千米"）
    dist_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:公里|km|KM|Km|千米)', text)
    # 也支持中文数字："十公里"="u4e94公里"等
    cn_num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
                  '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
                  '两': 2, '半': 0.5, '三十': 30, '四十': 40, '五十': 50}
    cn_dist_match = re.search(r'([一二三四五六七八九十两半]+)\s*(?:公里|千米)', text)

    if dist_match:
        target_distance = float(dist_match.group(1))
        # 根据距离和配速估算时长
        duration_min = round(target_distance * pace)
    elif cn_dist_match:
        cn_str = cn_dist_match.group(1)
        if cn_str in cn_num_map:
            target_distance = cn_num_map[cn_str]
        else:
            # 尝试拆解，如"二十五" = 25
            target_distance = 10  # 默认
            for k, v in sorted(cn_num_map.items(), key=lambda x: -len(x[0])):
                if cn_str.startswith(k):
                    target_distance = v
                    break
        duration_min = round(target_distance * pace)
    else:
        # 没有明确距离，用时间/配速计算
        target_distance = round(duration_min / pace, 2) if sport_type == '跑步' else round(duration_min / 60 * 18, 2)

    origin_name = ''
    dest_name = ''
    route_match = re.search(r'从\s*([^，。,；;]+?)\s*(?:到|去)\s*([^，。,；;]+)', text)
    if route_match:
        origin_name = route_match.group(1).strip()
        dest_name = route_match.group(2).strip()
        # 清理终点中可能包含的后续内容
        for sep in ['途经', '途径', '经过', '路过', '然后', '再', '要求', '需要', '希望']:
            if sep in dest_name:
                dest_name = dest_name.split(sep)[0].strip()

    via_names: List[str] = []
    via_match = re.search(r'(?:途经|途径|经过|路过)\s*(.+?)(?:\s*(?:要求|需要|希望|大约|大概|左右|然后|再|\d+\s*(?:分钟|小时|公里|km))|$)', text)
    if via_match:
        via_raw = re.sub(r'[，。,；;！!？?]+$', '', via_match.group(1).strip())
        via_names = [item.strip() for item in re.split(r'[、/，,和与及\s]+', via_raw) if item.strip() and len(item.strip()) >= 2]

    need_shade = any(k in text for k in ['树荫', '林荫', '遮阴', '遮荫'])
    need_water = any(k in text for k in ['补给', '水站', '饮水', '补水'])
    need_sea_view = any(k in text for k in ['海景', '海边', '沿海', '看海'])
    injury_flags = ['脚踝', '膝盖', '膝', '跟腱', '伤病', '不适']
    avoid_hard_surface = any(k in text for k in injury_flags)

    return {
        'sport_type': sport_type,
        'duration_min': duration_min,
        'target_distance_km': target_distance,
        'origin_name': origin_name,
        'dest_name': dest_name,
        'via_names': via_names,
        'need_shade': need_shade,
        'need_water': need_water,
        'need_sea_view': need_sea_view,
        'avoid_hard_surface': avoid_hard_surface,
        'preferred_surfaces': [],
        'district': '',
        'injury_notes': '用户提及伤病或不适' if avoid_hard_surface else '',
        'pace_min_per_km': pace,
        'special_requirements': [],
        'analysis_summary': f'基于规则兜底解析：{text[:80]}',
    }


def _chat_completion(messages: List[Dict[str, str]], model: str, *, json_mode: bool = False, max_tokens: int = 2000) -> str:
    if not client:
        raise RuntimeError('DeepSeek API Key 未配置')

    kwargs: Dict[str, Any] = {
        'model': model,
        'messages': messages,
        'max_tokens': max_tokens,
    }
    if json_mode:
        kwargs['response_format'] = {'type': 'json_object'}

    response = client.chat.completions.create(**kwargs)
    return _message_text(response.choices[0].message)


def _parse_json_payload(content: str) -> Dict[str, Any]:
    raw = (content or '').strip()
    if not raw:
        raise ValueError('empty model content')

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def parse_user_intent(user_message, conversation_history=None, user_profile=None):
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]

    if user_profile:
        profile_info = (
            f"\n用户信息：配速 {user_profile.get('avg_pace', 6.0)} min/km，"
            f"偏好 {user_profile.get('preferred_terrain', '公园步行道')}，"
            f"伤病 {json.dumps(user_profile.get('injury_history', []), ensure_ascii=False)}"
        )
        messages[0]['content'] += profile_info

    messages.extend(_safe_history(conversation_history, limit=6))
    messages.append({'role': 'user', 'content': user_message})

    try:
        content = _chat_completion(messages, CHAT_MODEL, json_mode=True, max_tokens=900)
        return _parse_json_payload(content)
    except Exception as exc:
        logger.error('DeepSeek intent parsing failed: %s', exc)
        fallback = _heuristic_intent(user_message, user_profile)
        fallback['error'] = str(exc)
        return fallback


def generate_route_commentary(route_info):
    distance = route_info.get('distance_km', 0)
    duration = route_info.get('duration_min', 0)
    shade_ratio = round(route_info.get('shade_ratio', 0) * 100)
    water_count = len(route_info.get('water_stations', []))
    terrain_types = route_info.get('terrain_types', [])
    terrain_text = '、'.join(terrain_types[:2]) if terrain_types else '综合路面'
    via_names = '、'.join(v.get('name', '') for v in route_info.get('via_points', []) if v.get('name'))
    via_text = f'，会绕经 {via_names}' if via_names else ''
    style = route_info.get('route_style', '智能推荐')

    if style == '最短直达':
        return (
            f"最短直达方案，全程约 {distance} 公里、{duration} 分钟，优先保证通达效率，"
            f"减少无效绕行；路面以 {terrain_text} 为主，遮荫率约 {shade_ratio}% ，沿线补给点 {water_count} 处。"
        )

    if style == '观景优先':
        sea_view_text = '，包含海景或观景视野加成' if route_info.get('has_sea_view') else ''
        return (
            f"观景优先方案，全程约 {distance} 公里、{duration} 分钟{via_text}，"
            f"优先串联更有景观价值的节点；路面以 {terrain_text} 为主，遮荫率约 {shade_ratio}% ，沿线补给点 {water_count} 处{sea_view_text}。"
        )

    if style == '林荫舒适':
        return (
            f"林荫舒适方案，全程约 {distance} 公里、{duration} 分钟{via_text}，"
            f"优先选择遮荫更好、体感更舒适的路段；路面以 {terrain_text} 为主，遮荫率约 {shade_ratio}% ，沿线补给点 {water_count} 处。"
        )

    return (
        f"{style}方案，全程约 {distance} 公里、{duration} 分钟{via_text}，"
        f"遮荫率约 {shade_ratio}% ，路面以 {terrain_text} 为主，沿线可利用补给点 {water_count} 处。"
    )


def generate_multi_turn_response(user_message, conversation_history=None, context=None):
    messages = [{'role': 'system', 'content': COACH_SYSTEM_PROMPT}]
    messages.extend(_safe_history(conversation_history, limit=8))

    if context:
        ctx_str = json.dumps(context, ensure_ascii=False)
        messages.append({'role': 'system', 'content': f'当前数据库信息：{ctx_str}'})

    messages.append({'role': 'user', 'content': user_message})

    try:
        content = _chat_completion(messages, REASONING_MODEL, max_tokens=420)
        is_route_request = '[ROUTE_REQUEST]' in content or _looks_like_route_request(user_message)
        clean_content = content.replace('[ROUTE_REQUEST]', '').strip()
        return {
            'response': clean_content or '已收到需求，正在为你生成路线方案。',
            'is_route_request': is_route_request,
        }
    except Exception as exc:
        logger.error('Multi-turn response failed: %s', exc)
        is_route_request = _looks_like_route_request(user_message)
        if is_route_request:
            return {
                'response': '已识别为路线规划需求，系统正在按规则引擎为你生成方案。',
                'is_route_request': True,
            }
        return {
            'response': '系统暂时无法连接到推理模型，请稍后重试。',
            'is_route_request': False,
        }


def get_model_runtime_info():
    return {
        'provider': 'DeepSeek',
        'base_url': _def_base_url,
        'reasoning_model': REASONING_MODEL,
        'chat_model': CHAT_MODEL,
        'reasoning_version': 'DeepSeek-V3.2 Thinking',
        'chat_version': 'DeepSeek-V3.2 Non-thinking',
        'configured': bool(client),
    }


def build_knowledge_context(query):
    knowledge_base = {
        '运动医学': [
            '脚踝不适时应避免硬地面跑步，推荐塑胶跑道或草地。',
            '膝盖问题应避免长下坡和台阶。',
            '热身不足容易导致肌肉拉伤。',
            '高温天气建议选择树荫较多的路线。',
        ],
        '厦门运动知识': [
            '环岛路是厦门最著名的跑步路线，全长约31公里。',
            '五缘湾湿地公园有专业塑胶跑道。',
            '仙岳山和狐尾山有完善的登山步道。',
            '海沧湾公园有标准塑胶跑道。',
            '集美学村周边有滨海绿道。',
        ],
    }

    relevant = []
    for category, items in knowledge_base.items():
        for item in items:
            if any(kw in query for kw in ['脚踝', '膝盖', '伤', '不适']) and category == '运动医学':
                relevant.append(item)
            if any(kw in query for kw in ['厦门', '环岛', '公园', '跑道', '步道']) and category == '厦门运动知识':
                relevant.append(item)
    return relevant
