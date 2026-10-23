# Sunbiz 定宽格式笔记（从数据反推，501/501 行对齐验证）

## 关键事实

- Sunbiz SFTP 文件是**定宽（fixed-width）格式**，不是分隔符格式。之前 adapter 里 `delimiter="|"` 的写法是错的，已确认废弃。
- Genfile（General Partnership）：每行 **759 字符**，无 header。
- 编码 latin-1。
- 日期格式：MMDDYYYY，空值 = 全 0（00000000）。

## Genfile 字段位置（759 定宽）

| 列范围 | 字段 | 样例 |
|---|---|---|
| [0:3] | 实体类型代码 | GP / LLP |
| [3:12] | 文档号（9 位） | 950001010 |
| [12] | 状态码 | A=Active, D=Dissolved, I=Inactive, E/R/C/V=其他（待官方对照） |
| [13:63] | 实体名称（50 字符，strip） | RANDOLPH SWAIN TALLENT & WHITEHEAD LLP |
| [63:205] | 扩展区（本样本未用，名称/备用） | — |
| [205:213] | 注册日期 MMDDYYYY | 09011995 |
| [213:221] | 注销日期 MMDDYYYY | 00000000 |
| [221:229] | 第三日期（待定） | 00000000 |
| [229:238] | FEI/EIN（9 位） | 593189815 |
| [238:240] | 州代码 | FL |
| [240:300] | 地址行 1（60 字符） | 900 WINDERLEY PLACE, SUITE 105 |
| [300:330] | 城市（30 字符） | MAITLAND |
| [330:332] | 州 | FL |
| [332:337] | 邮编（5 位） | 32751 |
| [337:460] | 邮寄地址区（第二地址块） | 8480 SW 168 TER... |
| [460:700] | 注册代理人区（AP 标记 + First/Middle/Last 名） | AP / RANDOLPH / ROBERT / F |
| [700:759] | 年报区（计数 + 最后年报日期） | ...09011996 |

## cordata.zip（Corporation+LLC 主数据，1.7GB，官方表实锤 2026-10-23）

- 10 个内层文件 cordata0-9.txt，**Deflate64（方法 9）**，须 Python 3.10 + zipfile_deflate64
- 行定宽 **1440 字符**（zip 流内行尾 \n 故读出 1442），12,987,601 行零坏行
- **官方 file-structure 权威表**（1-based 起始/长度，已逐项与实测咬合）：
  https://dos.fl.gov/sunbiz/other-services/data-downloads/corporate-data-file/file-structure/
  0-based 切片（入库 ingest_fl.py 采用）：
  - [0:12] Corporation Number（变长，DOC_RE 解析；8 条已知变体走 fallback）
  - [12:204] Corporation Name
  - [204] Status（A=Active / I=Inactive，官方原文）
  - [205:220] Filing Type（15 字符：DOMP/DOMNP/FORP/FORNP/DOMLP/FORLP/FLAL/FORL/NPREG/TRUST/AGENT）
  - [220:262] Address 1、[262:304] Address 2、[304:332] City、[332:334] State、[334:344] Zip（含 ZIP+4）
  - [472:480] **File Date**（MMDDYYYY，'00000000'=空）——即注册/成立日期
  - [480:494] FEI Number、[495:503] Last Transaction Date、[503:505] State Country
  - [505:586] 近三年年报区（Report Year/Date ×3）
  - [544:586] Registered Agent Name、[586:660] RA Type/Address/City/State/Zip
  - [669:1436] Officers ×6（Title/Type/Name/Address/City/State/Zip+4）
- ⚠️ 历史错误存档：本文件旧版曾写"[462:470] 注册日期"——那实为官方 **Mail Zip** 字段（[460:470]），系当年把邮寄邮编误当注册日期，已被官方表推翻废弃
- 实测行复核：L16000216990（FLIP THAT REO LLC）File Date=2016-11-30 与发号年 L16 自洽；[495:503]=Last Transaction Date 与官方字段名咬合
- 已知变体：8 条文档号格式变体（单数字/小写前缀/字母 O 冒充 0）、FEI 可为 'NOT APPLI'/全 0、个别未来日期源数据伪影（如 07/16/2120）
- 文档号前两位 ≈ 发号年（L25=2025 注册）；**主库快照存在水位**（本次 L26 最大序号 501467），快照后新发号只在日文件里

## 日文件双轨（doc/cor/ 实测 2026-10-23）

- `doc/cor/YYYYMMDDc.txt` = **当日新发号**（current filings）：100% 当年号段（L26/P26...），含 reinstatement 老公司新发号（原注册日照常显示）
- `doc/cor/Events/YYYYMMDDce.txt` = **当日事件**（全事件流，各年号段）：行格式 ≠ 主记录！布局 = 文档号 + 5位序号 + 事件代码(CORAPREIN等) + 事件描述(REINSTATEMENT/DISSOLUTION/AMENDMENT...) + 8位事件日期。**不能按 1440 主布局解析**
- 相邻两天 ce 文件可字节级相同（滚动窗口，非严格日增量）
- diff 管道数据源 = c（新实体）+ ce（状态/名称事件）双文件互补

## SFTP 结构

```
sftp.floridados.gov:22  Public / PubAccess1845!
doc/
├── Quarterly/                  ← 季度全量
│   ├── Cor/cordata.zip (1.7GB) + corevent.zip (186MB)
│   ├── Fic/ficdata.zip (74MB) + ficevt.zip (51MB)
│   ├── Non-Profit/npcordata.zip (41MB)
│   ├── Gen/Genfile.zip (3MB) + Genevt.zip (1.8MB)
│   └── TradeMarks/TMData.zip (11MB)
├── cor/                        ← 按天变动事件文件（diff 管道数据源！）
│   ├── 2011/...2021/（按年目录）
│   ├── 20220103c.txt ~ 现在（每天 ~2-3MB）
│   └── corindex.txt
└── notes/corindex.txt
```

## 对 diff 管道的意义

- `doc/cor/` 的按天事件文件 = 官方自带的变动流，**比我们自己做全量 diff 更精准**
- 周管道：拉过去 7 天的日文件 → 解析事件 → 直接写入 company_history
- 季度全量 zip 用于 baseline 入库

## 状态码对照（待补全，来源：样本统计）

| 代码 | 出现次数/501 | 推测含义 |
|---|---|---|
| A | 287 | Active |
| E | 159 | Exempt? / Existing? |
| C | 31 | Cancelled? |
| D | 7 | Dissolved |
| V | 7 | Voluntarily Dissolved? |
| I | 6 | Inactive |
| R | 4 | Registered (待确认) |
