# LLM Function Calling Agent：能读 Excel、查数据库的最小 Agent

> 手写 Function Calling 循环，不依赖 LangChain 等编排框架。核心代码约 420 行（含测试、数据脚本与文档共 920 行）。

模型通过 Function Calling 自主决定调用哪个工具（读 Excel / 查 SQLite），拿到真实数据后再作答，不靠编。

做它是为了回答一个具体问题：**Agent 和"聊天机器人"到底差在哪。** 差别不在模型，在循环——模型只负责决策，执行、校验、兜底全是代码的事。

---

## 一、5 分钟跑通

```bash
git clone https://github.com/LL7-1/llm-function-calling-agent.git
cd llm-function-calling-agent
pip install -r requirements.txt

# 1) 生成示例数据（60 条订单 + 4 个产品）
python scripts/make_sample.py

# 2) 不联网，先把两个工具和失败处理跑一遍（不需要 API Key）
python main.py --selftest

# 3) 跑测试（14 个，也不花钱）
python -m pytest -q
```

想真的让模型跑起来，再配 Key：

```bash
cp .env.example .env
# 打开 .env，填 DEEPSEEK_API_KEY（或 ZHIPU_API_KEY）
python main.py --q "华东地区一共卖了多少钱？哪个产品卖得最好？"
```

> 没有 Key 也能交差：`--selftest` 和 `pytest` 都不联网，能证明工具层和循环是对的。

---

## 二、目录结构

```
agent-demo/
├─ main.py               命令行入口（--selftest / --q / 交互模式）
├─ agent/
│  ├─ llm.py             三家大模型的统一客户端（OpenAI 兼容协议）
│  ├─ tools.py           两个工具 + 工具说明书 + 分发器
│  └─ loop.py            Agent 主循环
├─ scripts/make_sample.py 生成示例 Excel 与 SQLite
├─ data/                 sales.xlsx（3 个 sheet）、demo.db（2 张表）
└─ tests/                14 个测试，全部离线
```

---

## 三、三个设计决定（面试讲这三个就够）

### 1. 工具返回结构化结果，不返回自然语言

每个工具都返回 JSON：

```json
{"ok": true,  "data": "| region | 金额 | ... |"}
{"ok": false, "error_type": "forbidden_sql", "message": "...", "hint": "..."}
```

**为什么**：模型读 JSON 比读一段散文更稳，而且 `ok` 这个字段让模型能明确判断"刚才那步成没成"，而不是从一堆文字里猜。

### 2. 四类失败，各有出路

工具出错不抛异常，而是把错误分成四类返回，每一类都带 `hint` 告诉模型下一步怎么办：

| error_type | 什么情况 | 模型下一步 |
|---|---|---|
| `file_not_found` | 路径写错或文件不在 | hint 里列出同目录下的可用文件，换个路径重试 |
| `bad_args` | 参数缺失、sheet 名不存在、参数不匹配 | 看 hint 改成正确参数 |
| `forbidden_sql` | 非 SELECT 的写操作 | 重写成查询，或直接告诉用户做不到 |
| `tool_crash` | SQL 语法错、文件损坏等 | 看报错定位，拆小问题 |

**为什么**：工具报错时直接把异常抛出去，整个对话就断了；而这个 Demo 里报错本身就是模型下一步的输入。这是 Agent 和普通脚本最不一样的地方——**失败要能被消化，不是让程序崩掉。**

### 3. SQL 只读，在代码里拦，不靠提示词

`query_sqlite` 会检查语句是不是 `SELECT / WITH`，发现 `INSERT / UPDATE / DELETE / DROP` 直接拒绝，并且数据库用 `mode=ro` 只读模式打开。

**为什么**：提示词里写"请不要删数据"是没用的——模型可以被绕过。**权限必须落在代码里，不能落在提示词里。** 这一条是从企业工具的角度想问题，不是从 Demo 的角度。

---

## 四、换模型只改一个变量

`.env` 里改 `PROVIDER` 即可，三家都走 OpenAI 兼容协议，代码不用动：

| PROVIDER | base_url | 默认模型 | Key |
|---|---|---|---|
| `deepseek` | https://api.deepseek.com | deepseek-chat | DEEPSEEK_API_KEY |
| `zhipu` | https://open.bigmodel.cn/api/paas/v4 | glm-4-flash（有免费额度） | ZHIPU_API_KEY |
| `openai` | https://api.openai.com/v1 | gpt-4o-mini | OPENAI_API_KEY |

---

## 五、已验证 / 未验证

**已验证（本地跑过）**
- `python main.py --selftest` 六个场景：正常读表、sheet 不存在、文件不存在、正常查询、拒绝写操作、SQL 语法错。
- `python -m pytest -q` → **14 passed**，覆盖工具层 10 个 + 循环层 4 个（含"工具报错不中断""步数用尽体面退出""模型给出非法 JSON 参数不崩"）。
- 无 Key 时给出明确提示，不抛堆栈。

**未验证**
- 真实大模型的端到端效果（需要 API Key 才能跑）。填上 Key 之后先问这句：
  `python main.py --q "华东地区一共卖了多少钱？"` ，正常应看到至少一次 `query_sqlite` 调用。

---

## 六、面试怎么讲（30 秒）

> 我自己写了一个最小的 Agent Demo：模型通过 Function Calling 调两个工具，一个读 Excel、一个查 SQLite，拿到真实数据再回答，而不是凭印象说。
>
> 里面我主要想清楚三件事：一是工具返回结构化结果，让模型能判断上一步成没成；二是错误分四类返回，每类带 hint 告诉模型下一步怎么办，而不是让程序崩掉；三是 SQL 只读的权限写在代码里而不是提示词里——提示词可以被绕过，代码不行。
>
> 14 个测试全是离线的，用一个假的模型桩驱动循环，不花 API 额度也能验证循环对不对。

**大概率被追问的三个问题**

1. **「为什么不直接用 LangChain / Dify？」**
   → 这个 Demo 我故意手写循环，就是想搞清楚框架替我做了什么：消息回灌、工具分发、步数控制、失败处理。这四件事手写一遍才知道哪里会出问题，之后用框架也知道该看哪些地方。

2. **「工具调用失败了你怎么办？」**
   → 分四类，每类带 hint。关键是模型不能重复同一个错两次以上，所以 system prompt 里写明了"同一类错不要连续试两次"。

3. **「多轮 / 多个工具同时调怎么办？」**
   → 现在循环支持一次返回多个 tool_calls 并逐个执行；多轮上下文按消息序列保留。但**长对话的上下文压缩我没做**，这是已知缺口。

---

## 七、边界（别越线）

这是**个人练手的 Demo**，不是公司项目。写进简历时只能写"个人项目"，不能说成实习内容——面试官问一句"这是给哪个客户做的"就会露。

示例数据是脚本生成的假数据（`scripts/make_sample.py`），不是真实业务数据。
