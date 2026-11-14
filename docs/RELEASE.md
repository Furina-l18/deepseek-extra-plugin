# 发版流程

版本号出现在**三个地方**，必须保持一致，否则用户看到的版本会互相矛盾。

| 位置 | 字段 |
|---|---|
| `metadata.yaml` | `version: v1.5.0` |
| `main.py` | `CODE_VERSION = "1.5.0"` |
| `main.py` | `@register(..., "1.5.0")` |

用脚本检查：

```bash
python scripts/check_version.py
```

CI 也会跑这一步，不一致会直接失败。

---

## 步骤

### 1. 更新版本号

把上面三处改成新版本号。

### 2. 更新 CHANGELOG

在 `CHANGELOG.md` 顶部新增一段，写清「改了什么、为什么」，不要只写「优化」。

### 3. 提交并打 tag

```bash
git add -A
git commit -m "feat: xxx v1.5.1"
git tag -a v1.5.1 -m "影响核心 v1.5.1"
git push origin main
git push origin v1.5.1
```

### 4. 打发布包

用 `git archive` 而不是压缩整个目录，避免把 `.git`、`__pycache__` 带进去：

```bash
git archive --format=zip --prefix=astrbot_plugin_affect_core/ -o astrbot-plugin-affect-core.zip HEAD
```

检查包内文件：

```bash
python -c "import zipfile;z=zipfile.ZipFile('astrbot-plugin-affect-core.zip');print(len(z.namelist()));print('\n'.join(z.namelist()))"
```

### 5. 写 Release 正文

至少包含：

- 一句话说明这版做了什么
- 变更列表
- 升级方式（覆盖目录 / `git pull`）
- 是否需要迁移数据
- 压缩包的 SHA-256

### 6. 创建 Release

网页：<https://github.com/Furina-l18/deepseek-extra-plugin/releases/new> → 选 tag → 粘贴正文 → 上传 zip。

或用 API：

```bash
gh release create v1.5.1 astrbot-plugin-affect-core.zip \
  --title "影响核心 v1.5.1" \
  --notes-file release-notes.md
```

### 7. 发布后自检

- [ ] Release 页能打开，附件能下载
- [ ] README 顶部的 Release 徽章显示新版本号
- [ ] tag 指向的提交与 `main` 一致
- [ ] 从压缩包全新安装一遍，日志出现正确的 `code_version`

---

## 版本号规则

| 变化 | 版本 |
|---|---|
| 破坏性改动（配置项重命名、数据结构变更） | 主版本 +1 |
| 新功能、新配置项 | 次版本 +1 |
| 修 bug、文档、性能 | 修订号 +1 |

目前仍在 `1.x`，接口尚不稳定，破坏性改动可以接受，但必须在 CHANGELOG 里写明迁移方式。
