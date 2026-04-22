"""
Agent 智能体引擎
- 融合 DeepSeek 的多轮对话 Agent
- 支持上下文动态修改、完善用户需求
- 主动追问缺失信息
- 集成 RAG、知识图谱、长期记忆
"""
import json
import logging
import os
from typing import Dict, Any, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Agent 系统提示词
AGENT_SYSTEM_PROMPT = """你是「运动路线大师」的智能 Agent——一个专业的厦门运动路线规划 AI 教练。

你具备以下能力：
1. **RAG 知识检索**：你可以从知识库中检索到相关的运动知识、地理信息、路线数据。
2. **知识图谱**：你了解厦门各区域、路段、景观点之间的关系网络。
3. **长期记忆**：你能记住用户的偏好、运动习惯和历史路线。
4. **多轮对话**：你能根据上下文动态修改和完善用户需求。

你的工作流程：
1. 分析用户消息，结合历史对话和记忆理解真实意图。
2. 如果信息不足以生成路线，**主动追问**缺失的关键信息（起点、终点、时长、强度等），但不要一次问太多。
3. 当信息足够时，给出专业分析并在结尾加上 [ROUTE_REQUEST] 标记。
4. 利用 RAG 检索到的知识增强回答的专业性和准确性。
5. 参考用户的长期记忆，给出个性化建议。

追问策略：
- 如果用户只说了运动类型但没说距离/时长，追问偏好的运动时长或距离。
- 如果用户没有指定区域，可以根据记忆推荐或询问偏好区域。
- 如果用户提到伤病，主动建议安全的路面和强度。
- 每次最多追问1-2个关键问题，不要让用户觉得繁琐。

风格要求：
- 直接、专业、像资深教练。
- 不要空话套话。
- 控制在 300 字以内。
- 不使用 emoji。
- 当引用知识库信息时，自然融入回答中。
"""


def _get_client():
    """获取 OpenAI 兼容客户端"""
    from openai import OpenAI
    api_key = os.getenv('DEEPSEEK_API_KEY') or getattr(settings, 'DEEPSEEK_API_KEY', '')
    base_url = os.getenv('DEEPSEEK_BASE_URL') or getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)


def _get_agent_session(session_id: str, user_id: str):
    """获取或创建 Agent 会话"""
    from smart_engine.models import AgentSession
    session, _ = AgentSession.objects.update_or_create(
        session_id=session_id,
        defaults={'user_id': user_id}
    )
    return session


def _update_session_intent(session, new_info: dict):
    """增量更新会话意图"""
    current = session.current_intent or {}
    for k, v in new_info.items():
        if v and v not in ('', [], {}, None, 0, False):
            current[k] = v
    session.current_intent = current
    session.turn_count += 1
    session.save(update_fields=['current_intent', 'turn_count', 'updated_at'])


def _assess_intent_completeness(intent: dict) -> Dict[str, Any]:
    """评估意图完整度"""
    required_fields = {
        'sport_type': '运动类型',
        'target_distance_km': '目标距离',
    }
    optional_fields = {
        'origin_name': '起点',
        'dest_name': '终点',
        'need_shade': '遮荫需求',
        'need_water': '补给需求',
        'need_sea_view': '海景需求',
        'district': '区域',
    }

    missing_required = []
    missing_optional = []
    filled = []

    for field, label in required_fields.items():
        if intent.get(field):
            filled.append(label)
        else:
            missing_required.append(label)

    for field, label in optional_fields.items():
        if intent.get(field):
            filled.append(label)
        else:
            missing_optional.append(label)

    has_distance_or_duration = bool(intent.get('target_distance_km') or intent.get('duration_min'))
    completeness = len(filled) / (len(required_fields) + len(optional_fields))

    return {
        'completeness': round(completeness, 2),
        'is_sufficient': has_distance_or_duration and len(missing_required) == 0,
        'filled': filled,
        'missing_required': missing_required,
        'missing_optional': missing_optional[:2],  # 最多提示2个可选项
    }


def agent_chat(user_id: str, session_id: str, message: str,
               conversation_history: List[Dict] = None) -> Dict[str, Any]:
    """
    Agent 智能对话主入口
    融合 RAG + 知识图谱 + 长期记忆 + 多轮追问
    """
    from smart_engine.rag_engine import rag_context_for_chat, rag_search
    from smart_engine.memory_engine import (
        get_memory_context_for_chat, extract_memories_from_conversation
    )
    from smart_engine.knowledge_graph import query_graph

    # 1) 获取/创建 Agent 会话
    session = _get_agent_session(session_id, user_id)

    # 2) RAG 检索
    rag_context = rag_context_for_chat(message, top_k=5)
    rag_results = rag_search(message, top_k=3)

    # 3) 长期记忆
    memory_context = get_memory_context_for_chat(user_id)

    # 4) 知识图谱查询（提取关键实体）
    graph_context = ''
    keywords = _extract_keywords(message)
    if keywords:
        graph_results = query_graph(keywords[0], limit=5)
        if graph_results.get('nodes'):
            graph_parts = ["相关知识图谱实体："]
            for node in graph_results['nodes'][:5]:
                graph_parts.append(f"- {node['name']}（{node['type']}）")
            if graph_results.get('edges'):
                graph_parts.append("实体关系：")
                for edge in graph_results['edges'][:5]:
                    graph_parts.append(f"- {edge['source_name']} --[{edge['relation']}]--> {edge['target_name']}")
            graph_context = '\n'.join(graph_parts)

    # 5) 构建增强消息
    messages = [{'role': 'system', 'content': AGENT_SYSTEM_PROMPT}]

    # 注入上下文
    context_parts = []
    if memory_context:
        context_parts.append(memory_context)
    if rag_context:
        context_parts.append(rag_context)
    if graph_context:
        context_parts.append(graph_context)
    if session.current_intent:
        context_parts.append(f"当前累积意图：{json.dumps(session.current_intent, ensure_ascii=False)}")

    if context_parts:
        messages.append({
            'role': 'system',
            'content': '以下是辅助信息，请参考但不要直接暴露给用户：\n' + '\n\n'.join(context_parts)
        })

    # 加入历史对话
    if conversation_history:
        for msg in conversation_history[-8:]:
            role = msg.get('role', 'user')
            if role not in ('user', 'assistant'):
                role = 'user'
            content = str(msg.get('content', '')).strip()
            if content:
                messages.append({'role': role, 'content': content})

    messages.append({'role': 'user', 'content': message})

    # 6) 调用 DeepSeek
    client = _get_client()
    response_text = ''
    is_route_request = False

    if client:
        try:
            chat_model = os.getenv('DEEPSEEK_CHAT_MODEL') or getattr(settings, 'DEEPSEEK_CHAT_MODEL', 'deepseek-chat')
            reasoning_model = os.getenv('DEEPSEEK_REASONING_MODEL') or getattr(settings, 'DEEPSEEK_REASONING_MODEL', 'deepseek-reasoner')

            response = client.chat.completions.create(
                model=reasoning_model,
                messages=messages,
                max_tokens=500,
            )
            content = response.choices[0].message.content or ''
            if isinstance(content, list):
                content = ''.join(item.get('text', '') if isinstance(item, dict) else str(item) for item in content)
            response_text = content.strip()
        except Exception as e:
            logger.error(f"Agent DeepSeek 调用失败: {e}")
            response_text = ''

    # 7) 如果 DeepSeek 失败，使用规则引擎兜底
    if not response_text:
        response_text = _fallback_response(message, session, memory_context, rag_results)

    # 8) 判断是否为路线请求
    is_route_request = '[ROUTE_REQUEST]' in response_text or _is_route_request(message)
    response_text = response_text.replace('[ROUTE_REQUEST]', '').strip()

    # 9) 更新会话状态
    new_state = 'completed' if is_route_request else 'gathering'
    session.state = new_state
    session.turn_count += 1

    # 追问历史
    clarification = session.clarification_history or []
    clarification.append({'turn': session.turn_count, 'user': message, 'agent': response_text[:200]})
    session.clarification_history = clarification[-10:]  # 保留最近10轮
    session.save()

    # 10) 提取记忆
    extracted_memories = extract_memories_from_conversation(user_id, message, response_text)

    return {
        'response': response_text,
        'is_route_request': is_route_request,
        'session_state': new_state,
        'turn_count': session.turn_count,
        'rag_sources': [{'title': r['title'], 'category': r['category'], 'score': r['score']}
                        for r in rag_results],
        'memories_extracted': len(extracted_memories),
        'accumulated_intent': session.current_intent,
    }


def _extract_keywords(text: str) -> List[str]:
    """从文本中提取关键词"""
    import re
    # 提取地名、运动相关词
    patterns = [
        r'厦[门大][\u4e00-\u9fff]*',
        r'[\u4e00-\u9fff]{2,4}(?:路|道|山|湖|湾|园|桥|寺|庙|馆|场|站)',
        r'(?:跑步|骑行|徒步|步行|慢跑)',
        r'(?:海景|树荫|林荫|补给|水站)',
    ]
    keywords = []
    for p in patterns:
        matches = re.findall(p, text)
        keywords.extend(matches)
    return keywords[:5]


def _is_route_request(text: str) -> bool:
    """判断是否为路线请求"""
    keywords = ['路线', '跑步', '慢跑', '骑行', '徒步', '步行', '通勤', '配速',
                '公里', '分钟', '小时', '从', '到', '途经', '海景', '树荫', '规划']
    return any(kw in text for kw in keywords)


def _fallback_response(message: str, session, memory_context: str,
                       rag_results: list) -> str:
    """规则引擎兜底回复"""
    if _is_route_request(message):
        parts = ["已收到你的运动需求。"]
        if rag_results:
            parts.append(f"根据知识库，{rag_results[0]['content'][:80]}")
        parts.append("[ROUTE_REQUEST]")
        return ''.join(parts)

    # 通用回复
    return "你好，我是运动路线大师的 AI 教练。请告诉我你的运动需求，比如想跑多远、在哪个区域、有什么特殊要求，我来为你规划最佳路线。"


def get_agent_session_info(session_id: str) -> Dict[str, Any]:
    """获取 Agent 会话信息"""
    from smart_engine.models import AgentSession
    try:
        session = AgentSession.objects.get(session_id=session_id)
        return {
            'session_id': session.session_id,
            'user_id': session.user_id,
            'state': session.state,
            'turn_count': session.turn_count,
            'current_intent': session.current_intent,
            'clarification_count': len(session.clarification_history or []),
            'created_at': session.created_at.isoformat() if session.created_at else '',
            'updated_at': session.updated_at.isoformat() if session.updated_at else '',
        }
    except AgentSession.DoesNotExist:
        return {'error': f'会话 {session_id} 不存在'}
