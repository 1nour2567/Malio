# Malio 联邦规则交换系统详解

**日期**: 2026-05-20

---

## 一、什么是"规则"

Malio 的规则是一种 **DSL (Domain Specific Language)**，让 Agent 像为自己编程一样控制粒子身体的行为。它不是系统提示词 (system prompt) 层面的"请 XX"，而是**直接约束粒子引擎的物理参数**——规则一旦生效，粒子的速度、亮度、颜色就被真实修改了。

### 规则结构

```json
{
  "id": "agent_1716230400",
  "when": { "type": "time_gt", "val": "23:00" },
  "then": [
    { "target": "brightness", "op": "mult", "val": 0.5 },
    { "target": "speed", "op": "set", "val": 2.5 }
  ],
  "endWhen": { "type": "time_lt", "val": "06:00" },
  "priority": 0,
  "_hits": 42,
  "_score": 0.85,
  "_active": true,
  "_source": "local",
  "note": "用户说晚上暗一点，23:00后亮度减半"
}
```

| 字段 | 作用 |
|------|------|
| `when` | 触发条件：时间范围 / 空闲时长 / 事件 / 天气 |
| `then` | 生效时的操作：修改粒子参数 |
| `endWhen` | 失效条件（可选），到达后自动撤销 |
| `priority` | 优先级，系统规则 (sys_) 永远高于 agent 规则 |
| `_hits` | 每帧命中计数，衡量规则活跃度 |
| `_score` | VisualAgent 自动计算的质量评分 (0-1) |
| `_active` | 是否启用（低能量 / 冲突会被自动禁用） |
| `_source` | `local` = 本机创建，`federated` = 从其他实例导入 |

---

## 二、规则从何而来——五条生成路径

### 路径 1：系统内置 (5 条 `sys_` 规则)

前端的 `particle-rules.js` 在启动时自动注入 5 条系统规则，**最高优先级，不可被 Agent 覆盖**：

| 规则 ID | 条件 | 效果 |
|---------|------|------|
| `sys_night` | 23:00-05:00 | 亮度→0.35，速度→2.5，振幅×0.7 |
| `sys_idle` | 5 分钟无操作 | 速度→2.0，密度上限→0.7 |
| `sys_song_change` | 切歌事件 | 振幅瞬间×1.8，3 秒渐降回归 |
| `sys_density_guard` | 粒子数 > 500 | 密度上限→0.8 |
| `sys_daylight` | 06:00-12:00 | 亮度渐进升至 1.0 |

### 路径 2：用户自然语言 → Reasoner → 规则

这是核心路径。用户对 Malio 说"晚上暗一点"或"不要太亮"：

1. **Perception** 层获取时间、天气、用户人格状态
2. **Router** 判断意图为 `command`
3. **Reasoner** (LLM) 根据 `dj-persona.md` + 上下文生成 JSON 响应，其中 `rules` 字段包含规则定义
4. **Pipeline** 提取 `rules`，通过 `state_manager` 持久化到内存 + JSON 文件
5. **Feedback** 通过 WebSocket 推送给前端

Reasoner 的系统提示中明确要求：

```
当用户要求持久变化（如"暗一点""慢一点""不要太亮"），必须在 rules 字段输出规则。
不要在 response 里口头答应而不填 rules。
```

LLM 解析失败时的**兜底机制**：`_extract_rules_from_text()` 用正则匹配中文关键词（暗/亮/快/慢/晚上/XX 点），提取参数→构造规则。

### 路径 3：LLM 自主生成 (LLMAutonomous)

`agent/llm_autonomous.py` 定期触发 LLM 自主思考，Agent 可以根据当前上下文（天气、时间、用户行为）自主生成规则，无需等待用户指令。

### 路径 4：联邦导入

从其他 Malio 实例导入规则（详见第四部分）。

### 路径 5：前端直接创建

前端的 `particle-rules.js` 暴露了 `addRule(ruleJson)` API，任何前端组件可以通过 WebSocket 直接注入规则，无需经过 LLM。

---

## 三、规则的完整生命周期

```
用户说 "晚上暗一点"
       │
       ▼
┌─────────────┐     ┌──────────┐     ┌───────────┐
│  Reasoner   │────▶│ Pipeline │────▶│ Feedback  │
│  (LLM生成)  │     │ (存储规则) │     │ (WS推送)  │
└─────────────┘     └──────────┘     └─────┬─────┘
                                           │
       ┌───────────────────────────────────┘
       ▼
┌──────────────┐     ┌────────────────┐
│ ParticleRules│────▶│ Canvas 2D 引擎 │  每帧评估
│ (前端DSL引擎) │     │ (800粒子实时渲染) │
└──────┬───────┘     └────────────────┘
       │
       │ 每 30 秒 OODA 反馈
       ▼
┌──────────────┐     ┌────────────────┐
│  WebSocket   │────▶│  VisualAgent   │
│  rule_feedback│     │  (评分/合并/冲突) │
└──────────────┘     └────────────────┘
```

### 阶段 1：生成 (LLM → JSON)

Reasoner 输出：

```json
{
  "response": "好的，以后晚上 11 点之后我会暗一点。",
  "rules": [{
    "id": "agent_1716230400",
    "when": { "type": "time_gt", "val": "23:00" },
    "then": [{"target": "brightness", "op": "mult", "val": 0.5}],
    "endWhen": { "type": "time_lt", "val": "06:00" }
  }]
}
```

### 阶段 2：存储 (Pipeline → state_manager → JSON 文件)

Pipeline 将规则追加到 `agent_rules` 列表，state_manager 写入 `data/sessions/default.json`：

```
data/sessions/default.json
  ├── playback_state
  ├── chat_history
  └── agent_rules: [...]    ← 规则持久化在此
```

### 阶段 3：下发 (Feedback → WebSocket)

Feedback 通过 `push_rule(rule)` 将规则以 WebSocket 消息推送到前端：

```json
{
  "type": "rule",
  "rule": {
    "id": "agent_1716230400",
    "when": {...},
    "then": [...],
    ...
  }
}
```

### 阶段 4：执行 (前端 ParticleRules 引擎)

`particle-rules.js` 的 `evaluate(now)` 方法在**每帧**被调用：

1. 遍历所有活跃规则
2. 调用 `_checkCond(rule.when, ctx)` 评估触发条件
3. 条件满足 → `_applyActions(rule.then, ctx)` 修改粒子引擎的 `_targetParams`
4. 修改的参数直接驱动 Canvas 2D 渲染（亮度、速度、振幅、密度、颜色）

### 阶段 5：反馈 (OODA 闭环)

前端每 30 秒通过 WebSocket 将规则健康报告推送回后端：

```json
{
  "type": "rule_feedback",
  "feedback": [
    { "id": "agent_1716230400", "hits": 42, "active": true, "lastFire": 120, "priority": 0 }
  ]
}
```

这个反馈在 `main.py` 中被处理后**注入到 LLM 的下一轮上下文**（OODA 闭环第 1245 行），让 LLM 看到自己创建的规则是否真的在生效、是否需要调整。

---

## 四、VisualAgent 的规则治理（无 LLM 介入）

`agent/visual_agent.py` 中的 `_manage_rules()` 方法在每个 atmosphere 循环（30 秒）中自动运行，不消耗 LLM token。

### 4.1 质量评分（`_score_rule`）

```
score = f(hits, active, lifespan)

hits/50        → 基础分 (cap 1.0)
inactive       → ×0.2 (被禁用的规则大幅扣分)
0 hits + >1h   → ×0.1 (从未触发的旧规则严重惩罚)
hits > 10      → +0.15 (经验证的规则加分)
```

### 4.2 环境自适应

| 条件 | 动作 |
|------|------|
| 下雨/阴天 | 冷色调 (蓝) → 暖化 (蓝→红偏移) |
| 深夜 (23-06) | 速度上限 → 0.85，亮度上限 → 0.7，自动设置 `endWhen: 06:00` |
| 晴朗白天 | 解除夜间限制，恢复被暂存的原值 |
| 低能量 (< 0.2) | 禁用加速/高亮规则（Persona 物理约束） |

### 4.3 元规则 (meta-rules) — 用规则管理规则

**死规则归档**：
- 条件：0 hits + 超过 24 小时 + 已被禁用
- 操作：设置 `_archived: true`

**合并候选标记**：
- 条件：3+ 条规则操作同一参数 (如都在改 `speed`)
- 操作：标记 `_merge_candidate: [id1, id2, id3]`，供 LLM 审查

**冲突检测与自动降级**：
- 条件：同一参数同时有加速 (mult > 1) 和减速 (mult < 1) 规则生效
- 操作：`priority` 较低的一方被 `_active = False` + 标记 `_conflict_with`

---

## 五、"联邦" 规则交换——当前实现 vs 概念

### 5.1 实际实现：import/export API

当前代码里就是两个 REST 端点，本质是**规则的序列化/反序列化**——把 JSON 导出来，再导入另一个实例。

#### `GET /api/rules/export`

```bash
curl http://localhost:8007/api/rules/export
```

```json
{
  "rules": [
    {
      "id": "agent_1716230400",
      "when": { "type": "time_gt", "val": "23:00" },
      "then": [{ "target": "brightness", "op": "mult", "val": 0.5 }],
      "priority": 0,
      "_hits": 42,
      "_score": 0.85,
      "_source": "local"
    }
  ],
  "count": 12,
  "exported_at": "2026-05-20T20:30:00"
}
```

#### `POST /api/rules/import`

```bash
curl -X POST http://localhost:8007/api/rules/import \
  -H "Content-Type: application/json" \
  -d '{"rules": [...]}'
```

导入做了三件事：

```python
# 1. 去重：when 条件相同 → 跳过
existing_conds = {json.dumps(r["when"], sort_keys=True) for r in existing}
if w in existing_conds:
    dupes += 1; continue

# 2. 信任降级：外部规则分数打折
r["_score"] *= 0.7

# 3. 打标 + 追加
r["_source"] = "federated"
existing.append(r)
```

然后靠 VisualAgent 的评分周期自然验证：命中多的回升，死规则淘汰。**冲突时低分规则先被牺牲**——这算是一个隐式的"投票淘汰"机制。

### 5.2 什么没有实现——联邦学习意义上的缺口

"联邦"这个词暗示了**多实例间协作更新共享模型的分布式训练**，而当前代码缺少以下全部：

| 缺口 | 联邦学习中的做法 | 当前 Malio 状态 |
|------|-----------------|----------------|
| **聚合算法** | FedAvg / FedProx / 差分隐私 SGD | 无。只是 append 到本地列表，不合并参数 |
| **模型参数共享** | 各 client 上传梯度，server 聚合后下发 | 规则是离散的 JSON 对象，不是连续参数向量，无法做加权平均 |
| **通信协议** | gRPC / FL gRPC 双向流 | 两个无认证的 HTTP 端点，无 server-client 拓扑 |
| **差分隐私** | 梯度裁剪 + 高斯噪声，保证单个用户数据不可推断 | 无。`_created_reason` 字段直接暴露了原始对话意图 |
| **安全聚合** | 多方安全计算 (MPC) 或同态加密 | 无。明文传输 |
| **节点发现** | 目录服务 / P2P DHT | 无。需要人工交换 JSON |
| **拜占庭容错** | Krum / trimmed mean 过滤恶意节点 | 无。任何节点可以注入任意规则 |
| **版本控制** | 模型版本号 + 回滚 | 无。导入即覆盖，无法追溯 |

### 5.3 为什么这件事比 ML 联邦学习更难

ML 联邦学习依赖一个关键前提：**模型是连续参数的向量空间**，可以做梯度平均。而 Malio 的规则是**离散的符号化对象**——`when = time_gt 23:00`, `then = brightness × 0.5`。

无法对两条规则做"加权平均"：

```
规则A: when time_gt 23:00 → brightness × 0.5  (_score 0.85)
规则B: when time_gt 22:00 → brightness × 0.4  (_score 0.6)

"聚合"结果应该是什么？
- when 是 time_gt 22:30? (阈值平均)
- brightness 是 ×0.45? (值平均)
- 还是直接保留两条分别评估?
```

当前代码选择了第三条——保留全部，靠 VisualAgent 的评分机制自然淘汰。这在工程上是务实的（避免了符号聚合这个难题），但不再是"联邦学习"。

### 5.4 可能的真实联邦方案（设计构想）

如果要把 Malio 的规则交换做成真正的联邦学习，需要重新建模：

**方案 A：规则嵌入 + 聚类**
1. 将每条规则的 when/then 编码为 embedding 向量（规则文本 → sentence transformer）
2. 各 client 上传规则 embedding + 本地命中统计
3. Server 端对 embedding 做聚类（DBSCAN / HDBSCAN），同一簇的规则视为"等效"
4. 簇内的参数值做加权平均（权重 = 各 client 的 `_hits`）
5. 输出一条"共识规则"下发所有 client

**方案 B：A/B 测试式联邦评估**
1. Server 收集所有 client 的规则 → 去重 → 随机分发给不同 client
2. 各 client 在本地运行 7 天，收集 hits 和用户跳过率
3. Server 汇总 A/B 结果，选出统计显著更优的规则
4. 类似临床试验的 meta-analysis 流程

**方案 C：强化学习视角**
1. 把每条规则视为一个 action（在什么状态启动什么效果）
2. 状态 = (时间, 天气, 用户人格参数)
3. 各 client 上传 (state, rule_id, reward) 三元组（reward = 用户是否跳过）
4. Server 训练一个 light 模型（如决策树）来预测最优规则
5. 这个模型才是真正的联邦产物

---

### 5.5 当前实际能用的功能

在方案 A/B/C 实现之前，现有的 import/export 能做什么：

1. **跨设备同步**：笔记本和台式机之间手动交换规则配置
2. **种子规则集**：新用户导入一套精选的基础规则（类似 "新手配置包"）
3. **规则审计**：导出 JSON 检查 Agent 偷偷创建了什么规则（FOIA 精神）

这些功能是完整的。但"联邦"目前只是一个设计方向，代码层面尚未实现。

---

## 六、技术约束

| 约束 | 说明 |
|------|------|
| 最多 3 条 agent 规则 | Reasoner 的系统提示中明确限制，防止规则爆炸 |
| 系统规则不可覆盖 | `sys_` 前缀，优先级始终最高 |
| 规则热更新 | 通过 WebSocket 实时推送，无需刷新页面 |
| 跨 session 持久化 | 保存在 `data/sessions/default.json`，重启后恢复 |
| 单用户隔离 | `state_manager` 的 `user_id` 机制支持多用户独立规则空间 |
| LLM 解析容错 | 如果 LLM 返回的 JSON 格式错误，`_extract_rules_from_text()` 用正则兜底 |
