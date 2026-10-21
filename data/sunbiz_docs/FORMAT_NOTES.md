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

## cordata.zip（Corporation 主数据，1.7GB）

- 定宽但列布局**未确认**（与 Genfile 类似但字段更多）
- 下载后用 `_analyze_fl.py` 同样方法确认：行长分布 → 日期锚点 → 切片验证
- 确认后才写 import_fl.py

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
