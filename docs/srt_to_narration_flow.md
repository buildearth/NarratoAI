# SRT 生成解说文案调用流程文档

> 版本：v0.7.8 | 更新日期：2026-04-27

---

## 概述

项目中有两种从 SRT 字幕生成文案的模式：

| 模式 | 说明 | 输出 |
|------|------|------|
| 短剧混剪（Short Generate） | 从SRT提取关键爆点片段，生成混剪脚本 | 保留原声（OST=1） |
| 短剧解说（Short Drama Summary） | 从SRT生成完整解说文案脚本 | 解说+原声混合（OST=0/1） |

---

## 模式一：短剧混剪（Short Generate）

### 调用链

```
script_settings.py（UI按钮点击）
  → webui/tools/generate_script_short.py: generate_script_short()
    → app/services/SDP/generate_script_short.py: generate_script_result()
      → SDP/utils/step1_subtitle_analyzer_openai.py: analyze_subtitle()
          ├── PromptManager.get_prompt("short_drama_editing", "subtitle_analysis")
          │     → LLM调用：生成剧情梗概 + 情节点标题
          ├── PromptManager.get_prompt("short_drama_editing", "plot_extraction")
          │     → LLM调用：提取爆点时间戳
      → SDP/utils/step5_merge_script.py: merge_script()
          → 生成最终脚本JSON（OST=1，保留原声）
```

### 关键文件

| 层级 | 文件 |
|------|------|
| UI入口 | `webui/components/script_settings.py` |
| WebUI工具 | `webui/tools/generate_script_short.py` |
| 服务层 | `app/services/SDP/generate_script_short.py` |
| 字幕分析 | `app/services/SDP/utils/step1_subtitle_analyzer_openai.py` |
| 脚本合并 | `app/services/SDP/utils/step5_merge_script.py` |
| 提示词 | `app/services/prompts/short_drama_editing/subtitle_analysis.py` |
| 提示词 | `app/services/prompts/short_drama_editing/plot_extraction.py` |

### LLM 调用说明

**第一次调用**（字幕分析）：
- 提示词：`short_drama_editing/subtitle_analysis`
- 输入：字幕内容 + 自定义片段数量
- 输出 JSON：
```json
{
  "summary": "整体剧情梗概",
  "narrative_structure": {
    "setup": "开端阶段",
    "rising_action": "发展阶段",
    "climax": "高潮阶段",
    "resolution": "结局阶段"
  },
  "plot_titles": ["[开端] 情节点1", "[发展] 情节点2"]
}
```

**第二次调用**（爆点提取）：
- 提示词：`short_drama_editing/plot_extraction`
- 输入：字幕内容 + 剧情梗概 + 情节点标题
- 输出 JSON：包含每个爆点的时间戳和画面描述

---

## 模式二：短剧解说（Short Drama Summary）

### 调用链

```
script_settings.py（UI按钮点击）
  → webui/tools/generate_short_summary.py: generate_script_short_sunmmary()
      ├── 第一步：SubtitleAnalyzerAdapter.analyze_subtitle()
      │     → app/services/SDE/short_drama_explanation.py
      │     → PromptManager.get_prompt("short_drama_narration", "plot_analysis")
      │     → LLM调用：输出分段剧情分析文本
      │
      ├── 第二步：SubtitleAnalyzerAdapter.generate_narration_script()
      │     → app/services/SDE/short_drama_explanation.py
      │     → PromptManager.get_prompt("short_drama_narration", "script_generation")
      │     → LLM调用：输出解说脚本JSON
      │
      └── parse_and_fix_json() → 写入 session_state['video_clip_json']
```

### 关键文件

| 层级 | 文件 |
|------|------|
| UI入口 | `webui/components/script_settings.py` |
| WebUI工具 | `webui/tools/generate_short_summary.py` |
| 解说服务核心 | `app/services/SDE/short_drama_explanation.py` |
| 提示词-剧情分析 | `app/services/prompts/short_drama_narration/plot_analysis.py` |
| 提示词-脚本生成 | `app/services/prompts/short_drama_narration/script_generation.py` |

### LLM 调用说明

**第一次调用**（剧情分析）：
- 提示词：`short_drama_narration/plot_analysis`
- 输入：字幕内容
- 输出：分段剧情分析文本（Markdown格式）
```
**一、整体剧情概括：**
[剧情概括]

**二、分段剧情解析：**

**剧情段落 1：[段落主题]**
*   **时间戳：** [开始时间] --> [结束时间]
*   **内容概要：** [详细描述]
```

**第二次调用**（脚本生成）：
- 提示词：`short_drama_narration/script_generation`
- 输入：短剧名称 + 剧情分析 + 字幕内容
- 创作要素：黄金开场（3秒钩子）、爽点放大、悬念预埋、原声比例7:3
- 输出 JSON：
```json
{
  "items": [
    {
      "_id": 1,
      "timestamp": "00:00:01,000-00:00:05,500",
      "picture": "画面描述",
      "narration": "解说文案 或 '播放原片1'",
      "OST": 0
    }
  ]
}
```

---

## 输出脚本结构

两种模式最终都生成同一格式的 JSON 数组：

```json
[
  {
    "_id": 1,
    "timestamp": "00:00:01,000-00:00:05,500",
    "picture": "画面内容描述",
    "narration": "解说文案 或 '播放原片N'",
    "OST": 0
  }
]
```

| 字段 | 说明 |
|------|------|
| `_id` | 片段序号 |
| `timestamp` | 裁剪时间范围，格式 `HH:MM:SS,mmm-HH:MM:SS,mmm` |
| `picture` | 画面内容描述（供参考） |
| `narration` | 解说文案；若值为 `播放原片N` 则播放原声 |
| `OST` | 0=播解说音频，1=保留原声，2=动态裁剪保留原声 |

---

## LLM 服务层

两种模式均通过 `app/services/SDE/short_drama_explanation.py` 中的 `SubtitleAnalyzerAdapter` 调用 LLM，支持：

- **Gemini 原生 API**：`POST {base_url}/models/{model}:generateContent`
- **OpenAI 兼容 API**：`POST {base_url}/chat/completions`

关键参数：

| 参数 | 分析阶段 | 生成阶段 |
|------|----------|----------|
| `temperature` | 0.1（稳定） | 0.7~1.5（创意） |
| `max_tokens` | 4000 | 64000 |
