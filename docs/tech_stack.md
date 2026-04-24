# NarratoAI 技术方案文档

> 版本：v0.7.8 | 更新日期：2026-04-24

---

## 核心框架

| 技术 | 版本 | 用途 |
|------|------|------|
| Streamlit | >=1.45.0 | Web UI 框架，快速构建数据应用界面 |
| Pydantic | - | 数据模型验证和序列化 |
| Loguru | >=0.7.3 | 日志管理 |
| Tenacity | >=9.0.0 | 自动重试机制 |

---

## 视频处理

| 技术 | 版本 | 用途 |
|------|------|------|
| MoviePy | 2.1.1 | 视频剪辑、合成、音频混合 |
| FFmpeg | - | 底层视频编解码，支持硬件加速（NVENC/VAAPI/VideoToolbox） |
| Pillow | >=10.3.0 | 图像处理（帧提取、字幕渲染） |

---

## AI / LLM

统一 OpenAI 兼容架构（v0.7.7 重构），所有模型通过同一接口调用。

| 技术 | 版本 | 用途 |
|------|------|------|
| openai SDK | >=1.77.0 | 调用 OpenAI 及所有兼容提供商（DeepSeek、Qwen、SiliconFlow 等） |
| google-generativeai | >=0.8.5 | Gemini 原生 SDK |
| dashscope | >=1.24.6 | 阿里云 Qwen 原生 SDK |

支持的 LLM 提供商：OpenAI / DeepSeek / Gemini / Qwen / Moonshot / SiliconFlow

---

## TTS 文本转语音

| 引擎 | 接入方式 | 说明 |
|------|----------|------|
| Edge TTS | edge-tts 7.2.7 | 默认，免费，微软 |
| Azure Speech | azure-cognitiveservices-speech >=1.37.0 | 微软云，需 API Key |
| 腾讯云 TTS | tencentcloud-sdk-python >=3.0.1200 | 需 SecretId/Key |
| SoulVoice | HTTP API | 第三方 |
| Qwen3 TTS | HTTP API | 阿里云 |
| IndexTTS2 | HTTP API（本地） | 本地语音克隆 |
| 豆包 TTS | HTTP API | 字节跳动 |

---

## 音频处理

| 技术 | 版本 | 用途 |
|------|------|------|
| pydub | 0.25.1 | 音频剪辑、混合、格式转换 |
| 自研音量归一化 | - | `audio_normalizer.py`，智能调整音量平衡 |

---

## 字幕处理

| 技术 | 版本 | 用途 |
|------|------|------|
| pysrt | 1.1.2 | SRT 字幕文件解析和生成 |
| 自研字幕渲染 | - | 基于 MoviePy + Pillow 渲染字幕到视频 |

---

## 配置管理

| 技术 | 用途 |
|------|------|
| TOML（tomli >=2.2.1） | 配置文件格式 |
| 环境变量 | 敏感信息覆盖 |

---

## 状态管理

| 方案 | 说明 |
|------|------|
| 内存字典（默认） | 轻量单机部署 |
| Redis（可选） | 分布式/持久化状态 |

---

## 剪映集成

| 技术 | 用途 |
|------|------|
| pyJianYingDraft | 生成剪映草稿文件（.draft），支持视频轨、音频轨、字幕 |

---

## 部署

| 技术 | 用途 |
|------|------|
| Docker + Docker Compose | 容器化部署 |
| Makefile | 构建脚本 |

---

## 测试

| 技术 | 用途 |
|------|------|
| unittest | 单元测试框架 |

---

## 技术选型总结

整体偏向**快速落地**：
- Streamlit 省去前后端分离的复杂度
- MoviePy + FFmpeg 覆盖视频处理全链路
- LLM 层统一 OpenAI 兼容接口，降低多提供商接入成本
- 状态管理支持内存和 Redis 两种模式，兼顾轻量部署和生产扩展
