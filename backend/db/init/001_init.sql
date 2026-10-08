-- 由 docker-compose 挂载到 /docker-entrypoint-initdb.d，容器首次启动时执行。
--
-- ⚠⚠ 中文全文检索的坑（已实测确认）⚠⚠
--
--   PostgreSQL 默认的 'simple' 配置不会对中文分词：
--       to_tsvector('simple', '星澜科技的边缘计算网关')
--       => '星澜科技的边缘计算网关':1        ← 整句被当成【一个词】
--       to_tsquery('simple','边缘计算')      => 永远 false，0 行结果
--
--   连"预先把文本按空格切开"都不够：查询侧如果不分词，
--   plainto_tsquery('simple','边缘计算') 也是一个整词，照样匹配不上。
--
--   正确做法是两侧都分词：
--   1) 入库时：Python 侧用 jieba 切好，空格连接，写进 content_seg
--   2) 检索时：查询词也过 jieba，再拼成 to_tsquery('simple','边缘 & 计算')
--   3) tsv 从 content_seg 生成（to_tsvector 的两参数版本是 immutable，可以做生成列）
--
--   向量维度必须与所选 embedding 模型一致（bge-m3 = 1024），换模型要重建表。

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- --------------------------------------------------------------------------- --
-- 原始文档
-- --------------------------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS documents (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT        NOT NULL,
    title        TEXT,
    content      TEXT        NOT NULL,
    content_hash TEXT        NOT NULL UNIQUE,
    meta         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------- --
-- 分块
-- --------------------------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT      NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal      INT         NOT NULL,

    -- 原文。用于展示给用户看、以及引用溯源
    content      TEXT        NOT NULL,

    -- ★ 新增：jieba 分词结果（词与词之间用空格连接），由 Python 侧写入。
    --   为什么不能用生成列自动算？因为 SQL 里做不到中文分词，必须在外面算好再插。
    content_seg  TEXT        NOT NULL DEFAULT '',

    token_count  INT,
    meta         JSONB       NOT NULL DEFAULT '{}'::jsonb,

    -- ★ 改：从 content_seg 生成，中文才能被搜到
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('simple', content_seg)) STORED,

    parent_id    BIGINT      REFERENCES chunks(id) ON DELETE CASCADE,

    -- 向量列。维度必须和 embedding 模型一致，否则插入时报错。
    -- 当前模型：Qwen/Qwen3-Embedding-0.6B → 1024 维
    -- 维度对照表在 app/embedding.py 的 KNOWN_DIMS 里。
    -- ⚠ 换模型 = 换维度 = 必须改这里 + 重建表 + 重新入库，三者缺一不可。
    embedding    vector(1024)
);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks (document_id);

-- 词法通道：jieba 分词 + GIN 索引
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING GIN (tsv);

-- ★ 新增：兜底通道。tsv 完全没命中时，用三元组相似度捞一把
CREATE INDEX IF NOT EXISTS chunks_content_trgm_idx ON chunks USING GIN (content gin_trgm_ops);

-- 向量通道：HNSW + 余弦距离
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

-- ★ 新增：防止同一文档重复入库同一序号（增量重建时保证幂等）
CREATE UNIQUE INDEX IF NOT EXISTS chunks_document_ordinal_idx ON chunks (document_id, ordinal);