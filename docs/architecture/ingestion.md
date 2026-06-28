# 知识库摄入系统 (Ingestion Pipeline)

## 架构

```
上传文档 (.md / .txt)
  │
  ▼
KnowledgeDocument (SQLite/PostgreSQL)
  │
  ▼  [点击"消化"]
IngestionPipeline.ingest_text()
  │
  ├─ 1. 文本切分 (chunking)
  │     滑动窗口：800字符 + 100字符重叠
  │     智能断句：优先在段落/句号处断开
  │
  ├─ 2. 批量嵌入 (embedding)
  │     OpenAI text-embedding-3-small (1536维)
  │     批量大小：20条/批
  │
  ├─ 3. Milvus 写入
  │     删除旧 collection → 创建新 collection → 批量插入
  │     Metric: COSINE
  │
  └─ 4. Agent 失效
        agent_registry.remove(persona_id)
        下次提问时自动重建 Agent (连接新知识库)
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

消化会自动收集该军师的所有文档（包括 `pending`、`pending_reingest`、`ingested`），全量重建 Milvus 索引。

## 检索流程

```
用户提问 "如何应对困境？"
  │
  ▼
MilvusStore.search(persona_id, query_embedding, top_k=5)
  │
  ├─ collection name: junshituan_kb_{persona_id}
  ├─ 余弦相似度搜索
  └─ 返回 top 5 文本片段
  │
  ▼
Agent system prompt 注入检索结果
  → "参考资料: ... (出师表原文片段)"
```

## Milvus 部署模式

| 模式 | 配置 | 适用场景 |
|------|------|----------|
| Milvus Lite | `MILVUS_LITE=true` | 本地开发 (嵌入式，零依赖) |
| Milvus Standalone | `MILVUS_LITE=false` | 生产环境 (Docker) |

Docker 模式下 Milvus 依赖 etcd (元数据) 和 MinIO (对象存储)。
