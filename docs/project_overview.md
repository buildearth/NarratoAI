# NarratoAI 项目全面分析文档

> 版本：v0.7.8 | 更新日期：2026-04-24

---

## 一、项目定位

**NarratoAI** 是一个 AI 驱动的自动化影视解说工具，核心能力：
- 自动分析视频内容，生成解说文案
- 自动裁剪视频片段、生成配音、渲染字幕
- 支持导出到剪映草稿进行二次编辑

---

## 二、目录结构与模块职责

```
NarratoAI/
├── webui.py                    # 启动入口
├── config.example.toml         # 配置模板
├── requirements.txt            # 依赖
│
├── app/                        # 核心业务逻辑
│   ├── config/                 # 配置管理
│   │   ├── config.py           # TOML配置加载器
│   │   ├── defaults.py         # 默认值（默认用SiliconFlow的Qwen/GLM）
│   │   ├── audio_config.py     # 音频音量配置
│   │   └── ffmpeg_config.py    # FFmpeg硬件加速配置
│   │
│   ├── models/                 # 数据结构定义
│   │   ├── schema.py           # Pydantic模型（VideoClipParams等）
│   │   ├── const.py            # 常量（任务状态、文件类型）
│   │   └── exception.py        # 自定义异常
│   │
│   ├── services/               # 核心服务层
│   │   ├── task.py             # 任务调度主控（530行）
│   │   ├── voice.py            # TTS文本转语音（2271行，8种引擎）
│   │   ├── generate_video.py   # 视频合成（509行）
│   │   ├── merger_video.py     # 视频片段合并（677行）
│   │   ├── subtitle.py         # 字幕生成与渲染（462行）
│   │   ├── material.py         # 素材管理（579行）
│   │   ├── state.py            # 任务状态（内存/Redis）
│   │   ├── jianying_task.py    # 剪映草稿导出（241行）
│   │   │
│   │   ├── llm/                # 大模型服务层（v0.7.7重构）
│   │   │   ├── unified_service.py             # 统一调用接口
│   │   │   ├── manager.py                     # 提供商注册与管理
│   │   │   ├── openai_compatible_provider.py  # OpenAI兼容实现
│   │   │   ├── migration_adapter.py           # 旧代码兼容适配
│   │   │   └── validators.py                  # 输出格式验证
│   │   │
│   │   ├── documentary/        # 纪录片处理
│   │   │   └── frame_analysis_service.py      # 帧提取→视觉分析→文案生成
│   │   │
│   │   ├── SDP/                # 短剧混剪（Short Drama Pipeline）
│   │   │   └── generate_script_short.py       # 字幕分析→混剪脚本
│   │   │
│   │   └── prompts/            # 提示词管理系统
│   │       ├── manager.py / registry.py
│   │       ├── documentary/                   # 纪录片提示词
│   │       ├── short_drama_narration/         # 短剧解说提示词
│   │       └── short_drama_editing/           # 短剧编辑提示词
│   │
│   └── utils/                  # 工具函数
│       ├── video_processor.py  # 视频帧提取
│       ├── ffmpeg_utils.py     # FFmpeg封装
│       ├── gemini_analyzer.py  # Gemini视觉分析
│       └── qwenvl_analyzer.py  # Qwen视觉分析
│
├── webui/                      # Streamlit前端
│   ├── webui.py                # 页面主逻辑（433行）
│   ├── components/             # UI面板组件
│   │   ├── basic_settings.py   # 文件上传、LLM配置
│   │   ├── script_settings.py  # 脚本生成方式
│   │   ├── audio_settings.py   # TTS引擎、音色、音量
│   │   ├── video_settings.py   # 分辨率、宽高比
│   │   └── subtitle_settings.py # 字幕字体、颜色、位置
│   ├── tools/                  # 脚本生成工具
│   └── i18n/                   # 中英文国际化
│
├── resource/                   # 静态资源
│   ├── fonts/                  # 字幕字体
│   ├── songs/                  # 背景音乐
│   └── videos/                 # 示例素材
│
└── tests/                      # 单元测试
```

---

## 三、核心业务流程

### 纪录片模式

```
上传视频
  → frame_analysis_service.py 提取关键帧（默认每3秒1帧）
  → 分批调用视觉模型分析帧内容（默认10张/批）
  → 文本模型生成解说文案（含timestamp和OST标记）
  → 用户可编辑脚本
  → task.py 调度：
      ├── voice.py 生成TTS音频
      ├── 按timestamp裁剪视频片段
      ├── audio_merger.py 混合 TTS + 原声 + BGM
      ├── subtitle.py 生成并渲染字幕
      └── generate_video.py 合成最终MP4
```

### 短剧混剪模式

```
上传视频 + 字幕文件
  → SDP/generate_script_short.py 分析字幕剧情
  → LLM提取关键剧情点，生成混剪时间戳
  → 后续流程同纪录片模式
```

### 剪映草稿导出

```
生成脚本后 → jianying_task.py
  → 生成TTS音频
  → pyJianYingDraft 创建草稿（视频轨+音频轨+字幕）
  → 导出 .draft 文件 → 用户在剪映中继续编辑
```

---

## 四、OST（原声策略）说明

脚本中每条记录有 `OST` 字段，控制原声处理方式：

| OST值 | 含义 |
|-------|------|
| 0 | 仅保留解说，移除原声 |
| 1 | 严格按脚本timestamp裁剪，保留原声 |
| 2 | 根据TTS时长动态裁剪，保留原声 |

---

## 五、LLM架构

v0.7.7 重构为统一的 OpenAI 兼容架构，所有提供商通过同一接口调用：

```
unified_service.py
  ├── analyze_images()   → 视觉模型（帧分析）
  └── generate_text()    → 文本模型（文案生成）

支持提供商：OpenAI / DeepSeek / Gemini / Qwen / Moonshot / SiliconFlow
默认配置：视觉模型 Qwen3.5-122B，文本模型 GLM-5（均走SiliconFlow）
```

---

## 六、TTS引擎支持

`voice.py` 支持8种引擎：

| 引擎 | 说明 |
|------|------|
| Edge TTS | 默认，免费，微软 |
| Azure Speech | 微软云，需API Key |
| 腾讯云TTS | 需SecretId/Key |
| SoulVoice | 第三方 |
| Qwen3 TTS | 阿里云 |
| IndexTTS2 | 本地语音克隆 |
| 豆包TTS | 字节跳动 |

---

## 七、配置文件关键项

`config.toml`（从 `config.example.toml` 复制后修改）：

```toml
[app]
vision_openai_model_name = "Qwen/Qwen3.5-122B-A10B"  # 视觉模型
vision_openai_api_key = ""
vision_openai_base_url = "https://api.siliconflow.cn/v1"

text_openai_model_name = "Pro/zai-org/GLM-5"          # 文本模型
text_openai_api_key = ""
text_openai_base_url = "https://api.siliconflow.cn/v1"

[frames]
frame_interval_input = 3    # 帧提取间隔（秒）
vision_batch_size = 10      # 每批帧数
vision_max_concurrency = 2  # 并发数
```

---

## 八、快速上手路径

1. 复制 `config.example.toml` → `config.toml`，填入 API Key
2. `pip install -r requirements.txt`
3. `streamlit run webui.py --server.maxUploadSize=2048`
4. 浏览器打开 http://localhost:8501
5. 上传视频 → 选择脚本生成方式 → 生成脚本 → 生成视频

---

## 九、理解项目的推荐阅读顺序

1. `config.example.toml` — 了解所有可配置项
2. `app/models/schema.py` — 理解核心数据结构
3. `app/services/task.py` — 理解任务调度主流程
4. `app/services/documentary/frame_analysis_service.py` — 理解AI分析核心
5. `app/services/llm/unified_service.py` — 理解LLM调用方式
6. `webui/webui.py` — 理解前端交互逻辑
