# AstrBot GPT-Researcher 插件

为 AstrBot 添加 gpt-researcher 深度搜索支持。该插件允许用户在聊天中通过特定关键词触发研究任务，并接收格式化的研究报告。

## 功能特性

- **关键词触发**：当消息包含"研究"或"deepresearch"时自动触发研究
- **深度研究**：支持 gpt-researcher 的 deep research 模式，进行递归深度研究
- **进度回报**：可配置的进度回报频率（每10%）和时间间隔（60秒最小间隔）
- **多格式报告**：支持 HTML、Markdown、纯文本三种报告格式
- **文件发送**：可选择以文件附件形式发送报告（避免长文本刷屏）
- **权限控制**：支持好友限制、白名单检查，确保只有授权用户可触发研究
- **异步处理**：研究任务在后台异步执行，不阻塞主线程
- **任务管理**：支持查看研究状态、取消研究任务

## 安装要求

### 安装 gpt-researcher

插件需要 gpt-researcher 已安装并配置。

## 配置说明

插件提供以下可配置选项：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `gpt_researcher_path` | string | `D:\Program\gpt-researcher\` | gpt-researcher 安装路径 |
| `trigger_keywords` | list | `["研究", "deepresearch"]` | 触发研究的关键词列表 |
| `report_format` | string | `"html"` | 报告显示格式：`html`、`markdown`、`text` |
| `progress_report_frequency` | int | `10` | 进度回报频率（百分比） |
| `progress_report_min_interval_seconds` | int | `60` | 进度回报最小间隔（秒） |
| `deep_research_enabled` | bool | `true` | 是否启用深度研究模式 |
| `max_research_time_minutes` | int | `30` | 最大研究时间（分钟） |
| `whitelist_enabled` | bool | `false` | 启用白名单检查 |
| `whitelist` | list | `[]` | 白名单列表（用户ID/群组ID/UMO） |
| `friend_only` | bool | `false` | 仅限好友私聊触发 |
| `send_as_file` | bool | `true` | 以文件附件形式发送报告 |
| `gpt_researcher_config.report_type` | string | `"deep"` | gpt-researcher 报告类型 |
| `gpt_researcher_config.report_format` | string | `"APA"` | 学术报告格式（APA/MLA/IEEE等） |
| `gpt_researcher_config.language` | string | `"chinese"` | 研究报告语言 |

## 使用方法

### 1. 触发研究
在聊天中发送包含触发关键词的消息：
```
研究 人工智能的最新发展
```
或
```
deepresearch 量子计算的最新进展
```

### 2. 查看研究状态
```
/research_status
```

### 3. 取消研究
```
/cancel_research
```

## 报告格式说明

### HTML 格式
- 添加 CSS 样式，美观易读
- 支持标题、列表、引用等格式
- 适合在支持 HTML 的客户端查看

### Markdown 格式
- 保持 gpt-researcher 原始输出
- 适合在支持 Markdown 的客户端查看
- 包含原始引用和链接

### 纯文本格式
- 去除所有格式标记
- 简洁的文本内容
- 适合在纯文本环境中查看

## gpt-researcher 集成说明

### 格式化接口
gpt-researcher 本身提供 `REPORT_FORMAT` 配置选项，支持以下学术格式：
- `APA`：美国心理学会格式（默认）
- `MLA`：现代语言协会格式  
- `IEEE`：电气电子工程师学会格式
- `Chicago`：芝加哥格式
- `Harvard`：哈佛格式

这些格式通过 `gpt_researcher_config.report_format` 配置项设置。

### 进度回调
gpt-researcher 的 deep research 模式提供 `on_progress` 回调，插件利用此功能实现：
- 实时进度监控
- 可配置的进度回报频率
- 时间间隔限制避免刷屏

### 错误处理
插件包含完整的错误处理机制：
- gpt-researcher 导入失败处理
- 研究任务超时处理
- API 密钥缺失提示
- 网络错误重试机制

## 开发说明

### 代码结构
```
main.py                    # 主插件代码
_conf_schema.json          # 配置 schema
metadata.yaml              # 插件元数据
README.md                  # 使用文档
```

### 关键技术
1. **异步任务管理**：使用 `asyncio.create_task` 创建后台研究任务
2. **进度监控**：基于百分比变化和时间间隔的智能进度回报
3. **报告格式化**：Markdown 到 HTML/Text 的转换
4. **错误恢复**：完善的异常处理和用户反馈

### 扩展建议
1. 添加更多报告格式（如 PDF、Word）
2. 支持自定义研究模板
3. 添加研究结果缓存
4. 支持批量研究任务

## 常见问题

### Q1: gpt-researcher 导入失败
**A**: 检查 `gpt_researcher_path` 配置是否正确，或尝试在 AstrBot 环境中安装 gpt-researcher。

### Q2: 研究任务没有进度回报
**A**: 检查 gpt-researcher 是否支持 `on_progress` 回调，某些版本可能不提供此功能。

### Q3: 报告格式不正确
**A**: gpt-researcher 的 `REPORT_FORMAT` 配置的是学术格式，插件的 `report_format` 配置的是显示格式，两者不同。

### Q4: 研究任务超时
**A**: 调整 `max_research_time_minutes` 配置，或检查网络连接和 API 密钥。

## 版本历史

### v0.1.0 (2026-03-20)
- 初始版本发布
- 支持关键词触发研究
- 实现进度回报机制
- 提供三种报告格式

## 许可证

MIT License

## 作者

Java8ver64

## 致谢

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 优秀的聊天机器人框架
- [gpt-researcher](https://github.com/assafelovic/gpt-researcher) - 强大的自主研究代理
