# 松原 · 分析算子执行剖面仪

松原数据库教学研发组 6 人用真实 Python scan/filter/hash join/group 算子，复查一条分析查询的每一步输出。

## 场景与模块
上游是设备可靠性课程的采样文件、传感器表和分析需求。过去在白板画算子、手动算中间行数，再把截图发给助教；重复键丢失、空结果误判、输入版本变化后无法复现实验是三个痛点。本站保存数据集与有界计划 DSL，worker 真执行并保存不可变快照/逐步摘要，下游讲师和同学只读复查。

数据集录入/编辑、算子计划编排、执行队列、算子剖面/JSON导出、复现试算五个业务页面；管理员有审计。四个业务实体 datasets / plans / traces / replay_jobs(+replay_trials) 均贯穿数据库、模型、schema、service、controller、route、前端api/store/page。

## 复现试算（最小替换复现）
两次课的分组结果对不上时，助教要找「最少换掉哪些传感器的采样」即可用原算子复现后一次结果。
- **受理**：选两条已完成轨迹（两次存档）。算子步骤逐字相同、传感器表（sensor_id→zone/device_type，顺序无关）相同才受理；否则返回可恢复的 400 错误。
- **有改动传感器 ≤8**：按 `sensor_id` 比对两次 readings 的整组差异，超过 8 个直接拒绝。
- **整组替换 + 原算子**：每个候选子集把基准数据中这些传感器的**整组** readings 换成后一次存档的组（含新增/清空整组），再跑同一计划，以最终输出 SHA-256 与后一次结果比对。
- **最多 64 组合**：按替换数量从小到大枚举（先空集，再单传感器…），组合计数到 64 即止；这也是试算额度上限。
- **可恢复、不重复扣额度**：每个组合在 `replay_trials` 落一行（pending/running/done），worker 用 `SELECT ... FOR UPDATE SKIP LOCKED` 只认领 pending；中断的 running 行经「恢复试算」退回 pending，已完成组合绝不重跑，每个组合最多计费一次。
- **候选 vs 已证**：找到可复现组合但仍有更小组合未排除时只标 `candidate`；当严格更小的组合全部排除（试算为不一致）才升级 `proven`（已证最小）。64 预算用尽仍无匹配标 `exhausted`。
- 可在算子剖面页点「以此存档发起复现试算」，或在复现试算页选档、预检、发起，页面轮询展示进度、逐组合结果与候选/已证组合。

## 启动
```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
前端 http://localhost:18244 ；后端 http://localhost:19244/docs ；PostgreSQL localhost:17744，trace / tracepass / operatortrace。结束 `docker compose down -v --remove-orphans` 会删本地数据。

| 角色 | 账号 | 页面与权限 | 动作 |
|---|---|---|---|
| admin | admin@operator.local | 全部含审计 | 复核执行人与完成事件 |
| operator | operator@operator.local | 创建/编辑/执行/导出 | 新建计划并交给worker |
| viewer | viewer@operator.local | 只读和导出 | 观察轨迹，写接口403 |

密码统一 `Trace2026!`。密码PBKDF2，JWT八小时；演示凭据和密钥仅限本地，部署前更换。

## 一天剧本与种子
1. 09:00 operator 登录读取「松原日班温升采样」。
2. 09:05 查看12传感器、240采样，北场/南场/试验间三分区。
3. 09:10 新建 `shift-20261117` 数据集，备注 `daily-readings-20261117.json`。
4. 09:15 保存高于50度→按sensor_id连接→按zone平均的计划。
5. 09:20 提交 `shift-20261117`，观察worker排队到完成。
6. 09:25 逐算子复查输入/输出行数与结果预览。
7. 09:30 导出 `trace-<id>.json`，viewer只读验证。
8. 10:00 admin 查看审计。

seed三账号、三个数据集（240行日班、空数据、重复右键）、三个对应计划；另加同一传感器表/同一算子的两次课分组存档（仅传感器2、7整组采样有改动），用于复现试算。固定公式，无随机数；自然键补缺不覆盖用户修改，连续运行不新增。

## 算法与边界
这是教学内核模型，不是PostgreSQL执行器剖面。PostgreSQL真实保存业务元数据；Python worker真实计算表扫描、数值/相等筛选、构建哈希桶与内连接、Decimal累积分组。右表重复键保留倍数，空集合输出空集合。分组avg/sum保留6位小数，输出按规范JSON排序，SHA-256使用排序key紧凑JSON UTF-8；相同输入和计划结果摘要相同。每步输出输入/输出行数、耗时、明细、前5行与checksum。scan 的 input_rows=0 表示从源读取，detail.scanned_rows为扫描源行数；row_visits是扫描/过滤/哈希构建与探测/聚合各步逻辑行访问总和，不代表物理I/O。

DSL最多6步，首步仅scan readings；filter eq/gte/lte；hash_join仅readings.sensor_id=sensors.sensor_id且最多一次；group仅value的count/sum/avg。禁止eval、任意代码和任意SQL。最多100传感器、2000采样、10000连接输出行；超限失败，不保存部分结果。JSON非法、字段错误、非法算子、孤立引用、重复名有可恢复错误。任务使用Redis简单单消费者，进程崩溃后的running任务不自动重试，保留供人工复查后新建任务。

## 技术、目录与本地开发
Python3.11 / FastAPI / SQLAlchemy / psycopg / Redis / PostgreSQL16；原生 HTML/CSS/JS ES modules / nginx1.27。五服务frontend/backend/worker/db/redis均健康探针，命名卷数据库/Redis/共享产物。DB/Redis健康后启动backend，backend健康后启worker/frontend。

backend/src按models/schemas/services/controllers/routes/middlewares/config/constants/utils分层；backend/scripts/seed_demo.py；backend/migrations元数据建表版本。复现试算的纯组合/替换内核在services/replay_engine.py（无DB/Redis依赖，可单测），持久化与可恢复循环在services/replay.py，模型在models/replay.py。frontend/src按api/stores/pages/components/common/hooks/router/types/constants/utils分层。三共享组件table/status/feedback，两hooks forms/poll。角色/状态/算子枚举在backend/src/constants/enums.py与frontend/src/constants/enums.js；权限/auth、worker状态、operator校验、复现任务/试算状态、前端状态展示使用相同枚举值。请求追踪和全局错误中间件、JWT授权、业务审计贯穿模块。

石墨黄铜工程蓝图视觉，双字体Noto Sans SC/Space Mono来自Google Fonts，离线回退；响应桌面/平板/手机。环境变量见.env.example：COMPOSE_PROJECT_NAME、三端口、JWT_SECRET、SEED_DEMO。DATABASE_URL/REDIS_URL由Compose提供。SEED_DEMO启动失败只记日志。

本地后端：pip install -r backend/requirements.txt，设置DATABASE_URL、REDIS_URL、JWT_SECRET，在backend运行uvicorn src.main:app --reload；前端需代理/api，不支持file://。截图、测试、日志和报告在批次根test-artifacts/gb-4105，源码无测试产物。License MIT。
