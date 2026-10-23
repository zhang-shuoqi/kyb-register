-- kyb.db 基础 schema（v1，2026-10-23 定稿）
-- 原则：库 = 结构规范化（trim/大写/ISO日期/唯一键）+ raw 原样留底；
--       暗号→人话的翻译全部在渲染层字典做，不进库；
--       坏了不修，坏了全量重建（源文件已本地留底）。
-- 注意：FTS5 虚拟表与触发器由 build_fts.py 在四国插完后统一创建（先插数后建索引，省一半体积）。

-- 主表：每 (jurisdiction, company_number) 一行，只存"当前快照"
CREATE TABLE IF NOT EXISTS company (
  jurisdiction    TEXT NOT NULL,          -- 'gb' / 'sg' / 'au' / 'us_fl'
  company_number  TEXT NOT NULL,          -- 规范化后（trim/大写/UK补零8位/AU补零9位）
  name            TEXT NOT NULL,          -- 当前登记名（内部空白压缩）
  status_raw      TEXT,                   -- 状态暗号原词（如 I / REGD / Active）
  entity_type_raw TEXT,                   -- 类型暗号原词（如 FLAL / APTY / Private Limited Company）
  industry_raw    TEXT,                   -- 行业码原词（UK SIC / SG SSIC；AU/FL 暂空）
  filing_date     TEXT,                   -- 注册/成立日 ISO 8601（YYYY-MM-DD），未知=''
  dissolution_date TEXT,                  -- 注销日 ISO 8601，未知=''
  address         TEXT,                   -- 主登记地址（拼接单行），未知=''
  agent           TEXT,                   -- 注册代理人（仅 FL 有源字段），未知=''
  source_url      TEXT,                   -- 官方原始记录核对链接
  retrieved_at    TEXT NOT NULL,          -- 数据快照日（源文件 mtime，不是入库日）
  raw             TEXT NOT NULL,          -- 源行原文 JSON 留底，一字不改
  UNIQUE(jurisdiction, company_number)
);

-- 曾用名表：UK PreviousName_1-10 / SG former_entity_name1-15 / AU 同ACN曾用名行
CREATE TABLE IF NOT EXISTS previous_name (
  jurisdiction   TEXT NOT NULL,
  company_number TEXT NOT NULL,
  former_name    TEXT NOT NULL,
  changed_at     TEXT NOT NULL DEFAULT '',  -- ISO 或 ''（未知；用''而非NULL保证UNIQUE去重生效）
  src            TEXT NOT NULL,             -- 记录通道：uk_prev_col_N / sg_former_col / au_prev_row
  UNIQUE(jurisdiction, company_number, former_name, changed_at)
);
CREATE INDEX IF NOT EXISTS idx_prev_jcn ON previous_name(jurisdiction, company_number);

-- 变动事件表：上线后由每周 diff 管道写入（FL 日文件 / 各国周更），现在只留位
CREATE TABLE IF NOT EXISTS company_event (
  event_id        INTEGER PRIMARY KEY,
  jurisdiction    TEXT NOT NULL,
  company_number  TEXT NOT NULL,
  event_type_raw  TEXT,                     -- 官方事件码原词（如 CORAPREIN）
  event_date      TEXT,                     -- ISO
  detail          TEXT,                     -- 事件描述原文
  source_file     TEXT,                     -- 来源文件名（可回溯）
  ingested_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_jcn ON company_event(jurisdiction, company_number);
