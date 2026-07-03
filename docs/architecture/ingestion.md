# 知识库摄入与检索系统

## 摄入架构

```
上传文档 (.md / .txt)
  │
  ▼
KnowledgeDocument (PostgreSQL)
  │
  ▼  [点击"消化"]
IngestionPipeline.ingest_text()
  │
  ├─ 1. 文本切分 (chunking)
  │     滑动窗口：800字符 + 100字符重叠
  │     智能断句：优先在段落/句号处断开
  │
  ├─ 2. 双路编码 (dual encoding)
  │     ├─ Dense: BGE-small-zh-v1.5 → 512维向量
  │     └─ Sparse: BM25 → 稀疏向量
  │
  ├─ 3. Milvus 写入
  │     删除旧 collection → 创建新 collection → 批量插入
  │     Collection schema: id + text + embedding + sparse_vec + source
  │     Metric: COSINE (dense)
  │
  └─ 4. Agent 失效
        agent_registry.remove(persona_id)
        下次提问时自动重建 Agent (连接新知识库)
```

## 混合检索 (Hybrid Search)

系统使用 **Dense + BM25 混合搜索**，同时利用语义理解和关键词精确匹配：

```
用户提问 "出师表中如何论述亲贤臣远小人？"
  │
  ├─ Dense 搜索 (BGE, 60%权重)
  │     语义理解：检索意思相近的段落
  │     → "亲贤臣，远小人，此先汉所以兴隆也"
  │
  ├─ BM25 搜索 (40%权重)
  │     关键词精确匹配："亲贤臣" "远小人" "出师表"
  │     → 精确定位到包含这些词的原文章节
  │
  └─ WeightedRanker(0.6, 0.4) 重新排序
     → 返回 Top-K 混合排序结果
```

### 为什么需要混合搜索？

| 场景 | 纯向量搜索 | BM25 补充 |
|------|-----------|----------|
| 专有名词搜索（人名、地名） | 语义近似但可能漏掉 | 精确命中 |
| 古文原文搜索 | 古文嵌入效果一般 | 关键词直接匹配 |
| 口语化问题 | 语义理解好 | 辅助作用 |
| 长文本段落检索 | 语义归纳能力强 | 精确度补充 |

### BM25 实现

- **编码**：基于 `pymilvus.model.sparse.BM25EmbeddingFunction`
- **回退**：若 pymilvus 版本不支持，使用内置 TF-IDF 字符 bigram 编码器
- **维度**：动态哈希到 65535 维空间
- **存储**：Milvus `SPARSE_FLOAT_VECTOR` 字段

### 检索 API

```python
# 自动混合搜索（如果 sparse_vec 可用）
results = await pipeline.search(
    persona_id="zhuge-liang",
    query="如何应对困境？",
    top_k=5,
)
# 返回结果带 rank_type 标记："dense" 或 "hybrid"
```

## 文档唯一标识

**ID 规则**：`SHA256("{persona_id}:{filename}")[:24]`

- 同名文件覆盖 → ID 不变 → `updated_at` 更新 → `status = pending_reingest`
- 仅接受 `.md`、`.txt`、`.markdown` 格式
- 每个军师的知识库可以包含多个文档

## 摄入 API

### 上传文档

```
POST /api/admin/advisors/upload-text
Content-Type: multipart/form-data

persona_id: zhuge-liang
filename: chushibiao.md
title: 出师表
text: <纯文本内容>
```

### 消化

```
POST /api/admin/advisors/ingest
Content-Type: application/json

{"persona_id": "zhuge-liang"}
```

消化会自动收集该军师所有文档（`pending` + `pending_reingest` + `ingested`），全量重建 Milvus 索引（含 dense + sparse 向量）。

## 嵌入后端

| 配置 | 模型 | 维度 | 费用 |
|------|------|------|------|
| `LOCAL_EMBEDDING=true` (默认) | BAAI/bge-small-zh-v1.5 | 512 | 免费 |
| `LOCAL_EMBEDDING=false` | OpenAI text-embedding-3-small | 1536 | ¥0.14/M token |

切换嵌入后端需重新消化所有知识库。

## Milvus 部署

使用 Milvus Standalone (Docker)，依赖 etcd (元数据) 和 MinIO (对象存储)：

```bash
docker compose up -d milvus etcd minio
```

配置：
```env
MILVUS_HOST=localhost
MILVUS_PORT=19530
```
