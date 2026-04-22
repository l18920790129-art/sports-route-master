"""
长期记忆系统引擎
- 跨会话持久化用户偏好和运动习惯
- 自动从对话中提取和更新记忆
- 记忆衰减与重要性排序
"""
import json
import logging
import re
from typing import List, Dict, Any, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


def store_memory(user_id: str, memory_type: str, key: str, value: str,
                 importance: float = 0.5, metadata: dict = None) -> Dict[str, Any]:
    """存储或更新一条长期记忆"""
    from smart_engine.models import LongTermMemory

    mem, created = LongTermMemory.objects.update_or_create(
        user_id=user_id, memory_type=memory_type, key=key,
        defaults={
            'value': value,
            'importance': min(1.0, max(0.0, importance)),
            'metadata': metadata or {},
        }
    )
    if not created:
        mem.access_count += 1
        mem.save(update_fields=['access_count', 'last_accessed'])

    return {
        'status': 'updated' if not created else 'created',
        'key': key,
        'memory_type': memory_type,
    }


def recall_memories(user_id: str, memory_type: Optional[str] = None,
                    limit: int = 10) -> List[Dict[str, Any]]:
    """回忆用户的长期记忆"""
    from smart_engine.models import LongTermMemory

    qs = LongTermMemory.objects.filter(user_id=user_id)
    if memory_type:
        qs = qs.filter(memory_type=memory_type)

    memories = []
    for mem in qs[:limit]:
        mem.access_count += 1
        mem.save(update_fields=['access_count', 'last_accessed'])
        memories.append({
            'memory_type': mem.memory_type,
            'key': mem.key,
            'value': mem.value,
            'importance': mem.importance,
            'access_count': mem.access_count,
            'created_at': mem.created_at.isoformat() if mem.created_at else '',
            'last_accessed': mem.last_accessed.isoformat() if mem.last_accessed else '',
        })
    return memories


def extract_memories_from_conversation(user_id: str, message: str,
                                        response: str, intent: dict = None) -> List[Dict[str, Any]]:
    """从对话中自动提取记忆"""
    extracted = []

    # 1) 提取距离偏好
    dist_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:公里|km)', message)
    if dist_match:
        dist = float(dist_match.group(1))
        result = store_memory(user_id, 'preference', 'preferred_distance_km', str(dist), importance=0.7)
        extracted.append({**result, 'detail': f'偏好距离: {dist}km'})

    # 2) 提取时长偏好
    time_match = re.search(r'(\d+)\s*(?:分钟|min)', message)
    if time_match:
        mins = int(time_match.group(1))
        result = store_memory(user_id, 'preference', 'preferred_duration_min', str(mins), importance=0.6)
        extracted.append({**result, 'detail': f'偏好时长: {mins}分钟'})

    hour_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:小时|hour)', message)
    if hour_match:
        hours = float(hour_match.group(1))
        result = store_memory(user_id, 'preference', 'preferred_duration_min', str(int(hours * 60)), importance=0.6)
        extracted.append({**result, 'detail': f'偏好时长: {hours}小时'})

    # 3) 提取运动类型偏好
    sport_keywords = {'跑步': '跑步', '慢跑': '跑步', '骑行': '骑行', '单车': '骑行',
                      '徒步': '徒步', '步行': '步行', '快走': '步行'}
    for kw, sport in sport_keywords.items():
        if kw in message:
            result = store_memory(user_id, 'preference', 'preferred_sport', sport, importance=0.8)
            extracted.append({**result, 'detail': f'偏好运动: {sport}'})
            break

    # 4) 提取环境偏好
    env_prefs = {
        '树荫': ('need_shade', '需要树荫'),
        '林荫': ('need_shade', '需要林荫'),
        '海景': ('need_sea_view', '需要海景'),
        '海边': ('need_sea_view', '喜欢海边'),
        '补给': ('need_water', '需要补给站'),
        '水站': ('need_water', '需要水站'),
    }
    for kw, (key, desc) in env_prefs.items():
        if kw in message:
            result = store_memory(user_id, 'preference', key, 'true', importance=0.6)
            extracted.append({**result, 'detail': desc})

    # 5) 提取伤病信息
    injury_keywords = {'脚踝': '脚踝不适', '膝盖': '膝盖问题', '膝': '膝关节问题',
                       '跟腱': '跟腱问题', '腰': '腰部不适'}
    for kw, desc in injury_keywords.items():
        if kw in message:
            result = store_memory(user_id, 'habit', 'injury_note', desc, importance=0.9,
                                  metadata={'keyword': kw})
            extracted.append({**result, 'detail': f'伤病记录: {desc}'})

    # 6) 从意图中提取结构化信息
    if intent:
        if intent.get('origin_name'):
            result = store_memory(user_id, 'route_history', 'last_origin', intent['origin_name'], importance=0.5)
            extracted.append({**result, 'detail': f'最近起点: {intent["origin_name"]}'})
        if intent.get('dest_name'):
            result = store_memory(user_id, 'route_history', 'last_destination', intent['dest_name'], importance=0.5)
            extracted.append({**result, 'detail': f'最近终点: {intent["dest_name"]}'})
        if intent.get('district'):
            result = store_memory(user_id, 'preference', 'preferred_district', intent['district'], importance=0.6)
            extracted.append({**result, 'detail': f'偏好区域: {intent["district"]}'})

    return extracted


def get_memory_context_for_chat(user_id: str) -> str:
    """为聊天生成记忆上下文"""
    memories = recall_memories(user_id, limit=15)
    if not memories:
        return ''

    parts = ["以下是该用户的历史记忆："]
    by_type = {}
    for m in memories:
        t = m['memory_type']
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(m)

    type_labels = {
        'preference': '用户偏好',
        'habit': '运动习惯',
        'route_history': '路线历史',
        'feedback': '用户反馈',
        'context': '上下文',
    }

    for t, items in by_type.items():
        label = type_labels.get(t, t)
        parts.append(f"\n【{label}】")
        for item in items:
            parts.append(f"- {item['key']}: {item['value']}")

    return '\n'.join(parts)


def get_memory_stats(user_id: str) -> Dict[str, Any]:
    """获取用户记忆统计"""
    from smart_engine.models import LongTermMemory

    total = LongTermMemory.objects.filter(user_id=user_id).count()
    by_type = {}
    for item in LongTermMemory.objects.filter(user_id=user_id).values('memory_type').distinct():
        t = item['memory_type']
        by_type[t] = LongTermMemory.objects.filter(user_id=user_id, memory_type=t).count()

    return {
        'user_id': user_id,
        'total_memories': total,
        'by_type': by_type,
    }


def clear_user_memories(user_id: str) -> Dict[str, Any]:
    """清除用户所有记忆"""
    from smart_engine.models import LongTermMemory
    count, _ = LongTermMemory.objects.filter(user_id=user_id).delete()
    return {'deleted': count, 'user_id': user_id}
