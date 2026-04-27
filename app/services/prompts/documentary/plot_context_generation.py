#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 逐帧解说-剧情上下文生成
@File   : plot_context_generation.py
@Description: 根据字幕和角色介绍生成剧情简介、时间轴和全局角色图谱
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class PlotContextGenerationPrompt(TextPrompt):
    """生成纪录片/影视解说用剧情上下文提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="plot_context_generation",
            category="documentary",
            version="v1.0",
            description="根据 SRT 字幕和已知角色介绍生成剧情简介、时间轴和全局角色图谱",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["剧情分析", "角色图谱", "时间轴", "字幕解析", "结构化"],
            parameters=["movie_title", "known_characters", "subtitle_content", "custom_instruction"],
        )
        super().__init__(metadata)
        self._system_prompt = "你是一位资深的剧本拆解师兼数据结构化专家，只能输出合法 JSON 对象。"

    def get_template(self) -> str:
        return """${custom_instruction}

## 输入数据
- 电影名称：${movie_title}
- 已知角色介绍：
${known_characters}
- SRT 字幕参考：
${subtitle_content}

请严格根据以上输入完成分析，并仅输出合法 JSON 对象。"""
