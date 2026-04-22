"""
RAG（检索增强生成）引擎
- 基于 TF-IDF 向量化实现轻量级语义检索
- 从 GIS 数据库自动构建知识文档
- 支持运动医学、厦门地理等领域知识
"""
import hashlib
import json
import logging
import math
import re
from typing import List, Dict, Any, Optional

import numpy as np
from django.utils import timezone

logger = logging.getLogger(__name__)

# ─── 轻量级 TF-IDF 向量化器 ───

_STOP_WORDS = set('的了是在有和与或者这个那一不也都就而且但如果因为所以可以')


def _tokenize(text: str) -> List[str]:
    """简单中文分词（基于字符 bigram + 关键词）"""
    text = re.sub(r'[^\u4e00-\u9fff\w]', ' ', text.lower())
    tokens = []
    words = text.split()
    for w in words:
        if len(w) <= 1 and w in _STOP_WORDS:
            continue
        tokens.append(w)
        # 中文 bigram
        if any('\u4e00' <= c <= '\u9fff' for c in w):
            for i in range(len(w) - 1):
                bigram = w[i:i + 2]
                if bigram not in _STOP_WORDS:
                    tokens.append(bigram)
    return tokens


class TFIDFVectorizer:
    """轻量级 TF-IDF 向量化器，不依赖外部库"""

    def __init__(self):
        self.vocabulary = {}
        self.idf = {}
        self.fitted = False

    def fit(self, documents: List[str]):
        doc_count = len(documents)
        if doc_count == 0:
            return self
        df = {}
        vocab_set = set()
        for doc in documents:
            tokens = set(_tokenize(doc))
            vocab_set.update(tokens)
            for token in tokens:
                df[token] = df.get(token, 0) + 1

        self.vocabulary = {word: idx for idx, word in enumerate(sorted(vocab_set))}
        self.idf = {}
        for word, idx in self.vocabulary.items():
            self.idf[word] = math.log((doc_count + 1) / (df.get(word, 0) + 1)) + 1
        self.fitted = True
        return self

    def transform(self, text: str) -> List[float]:
        if not self.fitted or not self.vocabulary:
            return []
        tokens = _tokenize(text)
        tf = {}
        for t in tokens:
            if t in self.vocabulary:
                tf[t] = tf.get(t, 0) + 1
        total = len(tokens) or 1
        vector = [0.0] * len(self.vocabulary)
        for word, count in tf.items():
            idx = self.vocabulary[word]
            vector[idx] = (count / total) * self.idf.get(word, 1.0)
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


# ─── 全局向量化器实例 ───
_vectorizer = TFIDFVectorizer()
_is_index_built = False


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot  # vectors are already L2-normalized


def _make_doc_id(category: str, source_id: str) -> str:
    raw = f"{category}:{source_id}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ─── 知识构建 ───

def build_rag_index(force_rebuild: bool = False) -> Dict[str, Any]:
    """从 GIS 数据库和内置知识构建 RAG 索引"""
    global _is_index_built, _vectorizer
    from smart_engine.models import KnowledgeDocument

    if _is_index_built and not force_rebuild:
        count = KnowledgeDocument.objects.count()
        return {'status': 'already_built', 'document_count': count}

    docs_created = 0
    all_texts = []

    # 1) 从 GIS 数据库导入 POI
    try:
        from gis_engine.models import POI
        for poi in POI.objects.all()[:500]:
            doc_id = _make_doc_id('poi', str(poi.id))
            content = f"{poi.name}是厦门{poi.district or ''}的{poi.get_poi_type_display() if hasattr(poi, 'get_poi_type_display') else poi.poi_type}。"
            if poi.address:
                content += f"地址：{poi.address}。"
            KnowledgeDocument.objects.update_or_create(
                doc_id=doc_id,
                defaults={
                    'category': 'poi',
                    'title': poi.name,
                    'content': content,
                    'source_type': 'database',
                    'source_id': str(poi.id),
                    'metadata': {'district': poi.district, 'poi_type': poi.poi_type,
                                 'lng': poi.lng, 'lat': poi.lat},
                }
            )
            all_texts.append(content)
            docs_created += 1
    except Exception as e:
        logger.warning(f"POI导入失败: {e}")

    # 2) 从 GIS 数据库导入路段
    try:
        from gis_engine.models import RoadSegment
        for road in RoadSegment.objects.all()[:300]:
            doc_id = _make_doc_id('road', str(road.id))
            shade_desc = {0: '无遮荫', 1: '少量遮荫', 2: '部分遮荫', 3: '较多遮荫', 4: '大量遮荫', 5: '全遮荫'}.get(road.shade_level, '未知')
            content = f"{road.name}是厦门{road.district or ''}的一条运动路段，路面类型为{road.surface_type}，长度约{road.length_m:.0f}米，遮荫程度为{shade_desc}。"
            if road.has_sea_view:
                content += "该路段拥有海景视野。"
            KnowledgeDocument.objects.update_or_create(
                doc_id=doc_id,
                defaults={
                    'category': 'road',
                    'title': road.name,
                    'content': content,
                    'source_type': 'database',
                    'source_id': str(road.id),
                    'metadata': {'district': road.district, 'surface_type': road.surface_type,
                                 'shade_level': road.shade_level, 'has_sea_view': road.has_sea_view},
                }
            )
            all_texts.append(content)
            docs_created += 1
    except Exception as e:
        logger.warning(f"路段导入失败: {e}")

    # 3) 从 GIS 数据库导入景观点
    try:
        from gis_engine.models import ScenicViewpoint
        for sv in ScenicViewpoint.objects.all()[:200]:
            doc_id = _make_doc_id('scenic', str(sv.id))
            content = f"{sv.name}是厦门{sv.district or ''}的{sv.view_type or '观景'}景观点。"
            if sv.description:
                content += sv.description
            KnowledgeDocument.objects.update_or_create(
                doc_id=doc_id,
                defaults={
                    'category': 'scenic',
                    'title': sv.name,
                    'content': content,
                    'source_type': 'database',
                    'source_id': str(sv.id),
                    'metadata': {'district': sv.district, 'view_type': sv.view_type,
                                 'lng': sv.lng, 'lat': sv.lat},
                }
            )
            all_texts.append(content)
            docs_created += 1
    except Exception as e:
        logger.warning(f"景观点导入失败: {e}")

    # 4) 内置运动医学知识
    sports_medicine_docs = [
        ("脚踝保护建议", "脚踝不适时应避免硬地面跑步，推荐塑胶跑道或草地。建议穿着支撑性好的跑鞋，跑前充分热身脚踝关节。"),
        ("膝盖保护建议", "膝盖问题应避免长下坡和台阶，建议选择平坦路面。可以使用护膝，控制跑量循序渐进。"),
        ("热身建议", "热身不足容易导致肌肉拉伤。建议跑前进行5-10分钟动态拉伸，包括高抬腿、侧弓步等。"),
        ("高温跑步建议", "高温天气建议选择树荫较多的路线，避开正午时段。注意补水，每15-20分钟补充150-200ml水分。"),
        ("配速建议", "初跑者建议配速6-7分钟/公里，进阶跑者可控制在5-6分钟/公里。长距离训练应降低配速10-15%。"),
        ("跑步姿势", "正确跑姿：身体微前倾，脚掌中前部着地，步频维持在170-180步/分钟。避免过度跨步。"),
        ("恢复建议", "长距离跑后建议48小时恢复期，可进行轻度拉伸和泡沫轴放松。蛋白质摄入有助肌肉修复。"),
        ("骑行安全", "骑行时务必佩戴头盔，夜间骑行需配备前后灯。厦门环岛路骑行建议走专用骑行道。"),
    ]
    for title, content in sports_medicine_docs:
        doc_id = _make_doc_id('sports_medicine', title)
        KnowledgeDocument.objects.update_or_create(
            doc_id=doc_id,
            defaults={
                'category': 'sports_medicine',
                'title': title,
                'content': content,
                'source_type': 'manual',
            }
        )
        all_texts.append(content)
        docs_created += 1

    # 5) 厦门运动知识
    xiamen_docs = [
        ("环岛路跑步", "环岛路是厦门最著名的跑步路线，全长约31公里，沿途可欣赏海景。从会展中心到黄厝段最受跑者欢迎，路面平坦，海风宜人。"),
        ("五缘湾湿地公园", "五缘湾湿地公园有专业塑胶跑道，环境优美，空气清新。公园内有多个饮水点和休息区，适合各水平跑者。"),
        ("仙岳山步道", "仙岳山有完善的登山步道系统，海拔约212米。步道包括石阶路和土路，适合越野跑和徒步训练。"),
        ("海沧湾公园", "海沧湾公园有标准塑胶跑道，全长约3.5公里。沿海而建，视野开阔，是海沧区最受欢迎的跑步场所。"),
        ("集美学村绿道", "集美学村周边有滨海绿道，连接集美大桥和杏林湾。路面以沥青和塑胶为主，适合长距离慢跑。"),
        ("狐尾山步道", "狐尾山位于思明区，有气象台观景平台。登山步道约2公里，坡度适中，适合晨跑和体能训练。"),
        ("筼筜湖环湖跑", "筼筜湖环湖一圈约6公里，是厦门市中心最便利的跑步路线。沿途绿化好，有多个公园入口。"),
        ("厦门马拉松赛道", "厦门马拉松赛道沿环岛路设置，起点在会展中心。赛道平坦，海拔起伏小，是PB（个人最好成绩）赛道。"),
        ("同安湾绿道", "同安湾绿道连接翔安和同安，全长约20公里。路面平整，沿途有红树林湿地景观。"),
        ("植物园跑步", "厦门植物园内有多条步道，总长约10公里。林荫覆盖率高，夏季跑步体感温度比市区低3-5度。"),
    ]
    for title, content in xiamen_docs:
        doc_id = _make_doc_id('xiamen_knowledge', title)
        KnowledgeDocument.objects.update_or_create(
            doc_id=doc_id,
            defaults={
                'category': 'xiamen_knowledge',
                'title': title,
                'content': content,
                'source_type': 'manual',
            }
        )
        all_texts.append(content)
        docs_created += 1

    # 构建 TF-IDF 索引
    if all_texts:
        _vectorizer.fit(all_texts)
        # 为所有文档生成嵌入
        for doc in KnowledgeDocument.objects.all():
            embedding = _vectorizer.transform(doc.content)
            if embedding:
                doc.embedding = embedding
                doc.save(update_fields=['embedding'])

    _is_index_built = True
    total = KnowledgeDocument.objects.count()
    logger.info(f"RAG 索引构建完成：共 {total} 篇文档")
    return {'status': 'built', 'document_count': total, 'new_docs': docs_created}


def _ensure_index():
    """确保索引已构建"""
    global _is_index_built, _vectorizer
    if not _is_index_built:
        from smart_engine.models import KnowledgeDocument
        count = KnowledgeDocument.objects.count()
        if count > 0:
            # 从已有文档重建向量化器
            all_texts = list(KnowledgeDocument.objects.values_list('content', flat=True))
            _vectorizer.fit(all_texts)
            _is_index_built = True
        else:
            build_rag_index()


# ─── RAG 检索 ───

def rag_search(query: str, top_k: int = 5, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """基于语义相似度检索相关知识文档"""
    _ensure_index()
    from smart_engine.models import KnowledgeDocument

    query_vec = _vectorizer.transform(query)
    if not query_vec:
        return []

    qs = KnowledgeDocument.objects.all()
    if category:
        qs = qs.filter(category=category)

    results = []
    for doc in qs:
        if not doc.embedding:
            continue
        sim = _cosine_similarity(query_vec, doc.embedding)
        if sim > 0.05:  # 相似度阈值
            results.append({
                'doc_id': doc.doc_id,
                'category': doc.category,
                'title': doc.title,
                'content': doc.content,
                'score': round(sim, 4),
                'metadata': doc.metadata,
            })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]


def rag_context_for_chat(query: str, top_k: int = 5) -> str:
    """为聊天生成 RAG 上下文字符串"""
    results = rag_search(query, top_k=top_k)
    if not results:
        return ''

    context_parts = ["以下是从知识库中检索到的相关信息："]
    for i, r in enumerate(results, 1):
        context_parts.append(f"{i}. [{r['category']}] {r['title']}：{r['content']}")
    return '\n'.join(context_parts)


def get_rag_stats() -> Dict[str, Any]:
    """获取 RAG 系统统计信息"""
    from smart_engine.models import KnowledgeDocument
    total = KnowledgeDocument.objects.count()
    by_category = {}
    for doc in KnowledgeDocument.objects.values('category').distinct():
        cat = doc['category']
        by_category[cat] = KnowledgeDocument.objects.filter(category=cat).count()
    return {
        'total_documents': total,
        'by_category': by_category,
        'index_built': _is_index_built,
        'vocabulary_size': len(_vectorizer.vocabulary) if _vectorizer.fitted else 0,
    }
