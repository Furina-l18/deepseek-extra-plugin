# 贡献指南

感谢愿意花时间改这个插件。它本质上是一个「行为拟合」实验，所以**行为变化的可解释性**比代码风格更重要。

---

## 开发环境

```bash
# 1. 把仓库放到 AstrBot 的插件目录
cd <AstrBot>/data/plugins
git clone https://github.com/Furina-l18/deepseek-extra-plugin astrbot_plugin_affect_core

# 2. 本地模型
ollama pull deepseek-r1:8b

# 3. 校验语法与配置
python -m compileall -q .
python scripts/check_version.py
```

不需要额外依赖：插件只使用标准库与 AstrBot 提供的 API。

---

## 代码结构

| 文件 | 职责 | 改动时的注意点 |
|---|---|---|
| `main.py` | 调度、钩子、命令、页面 API | 钩子优先级不能随意调，会改变注入顺序 |
| `mood_engine.py` | 激素 → 八维 → 情绪 → 性格 | 模型参数改动会影响所有人的观感 |
| `energy_engine.py` | 昼夜曲线与接话率 | 曲线节点改动会直接改变机器人活跃时段 |
| `taxonomy.py` | 情感类型、事件权重、神经画像 | 权重表是行为核心，改动请附理由 |
| `analyzer.py` | Ollama 调用与结果校验 | 结构化输出的容错逻辑不要轻易删 |
| `insult.py` | 辱骂识别与语境消歧 | 词表和消歧规则要一起改，否则误判率会上升 |
| `style.py` | 说话风格统计 | 只统计可量化指标，不要加主观判断 |
| `learn.py` | 记忆库抽取与召回 | 宁可不记，也不要记错 |

---

## 提交前检查清单

- [ ] `python -m compileall -q .` 通过
- [ ] `python scripts/check_version.py` 通过（版本号三处一致）
- [ ] `_conf_schema.json` 能被 `json.load` 解析
- [ ] 没有提交 `data/`、`plugin_data/`、`*.log`、`pages/affect/data.json`
- [ ] 没有真实的 QQ 号、群号、昵称或截图
- [ ] 新增配置项在 README 的配置表里补了一行
- [ ] 行为有变化时，在 CHANGELOG 里写了「改了什么、为什么」

---

## 提交信息

使用 `<type>: <subject>` 格式：

| type | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | 修 bug |
| `docs` | 文档 |
| `refactor` | 不改行为的重构 |
| `perf` | 性能 |
| `chore` | 构建、依赖、杂项 |

示例：

```
feat: 支持配置推理模型
fix: 修复能量在跨天时归零的问题
docs: 补充睡眠债的计算说明
```

---

## Pull Request

1. Fork 或新建分支（`feat/xxx`、`fix/xxx`）
2. 保持改动聚焦，一个 PR 只做一件事
3. 在描述里写清楚：
   - 改了什么
   - 为什么改
   - 对行为的影响（尤其是情感、能量、辱骂判定这三块）
4. 涉及参数调整的，附上改动前后的对比（例如同一段对话下情感分的变化）

---

## 敏感信息

这个插件接触的是真实聊天记录，因此**默认假设任何数据都敏感**：

- 不要截图真实群聊、昵称、QQ 号
- 需要示例数据时，自己编造（如小林、阿澈、老王）
- 调试日志里出现的个人信息，提交前删掉

---

## 发版流程

见 [docs/RELEASE.md](docs/RELEASE.md)。

---

## 行为改动的基本原则

这个插件的目的不是「让机器人更聪明」，而是「让行为更像人」。所以改动时请优先考虑：

1. **可解释**：参数改动要能说清楚对应哪种人类行为
2. **可回退**：新逻辑尽量做成配置项，默认值保持原有行为
3. **不过度**：宁可弱一点，也不要把机器人变成情绪化的怪物
