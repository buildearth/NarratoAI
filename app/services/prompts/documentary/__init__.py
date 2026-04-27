#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : __init__.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 纪录片解说提示词模块
"""

from .frame_analysis import FrameAnalysisPrompt
from .narration_generation import NarrationGenerationPrompt
from .plot_context_generation import PlotContextGenerationPrompt
from ..manager import PromptManager


def register_prompts():
    """注册纪录片解说相关的提示词"""
    
    # 注册视频帧分析提示词
    frame_analysis_prompt = FrameAnalysisPrompt()
    PromptManager.register_prompt(frame_analysis_prompt, is_default=True)
    
    # 注册解说文案生成提示词
    narration_prompt = NarrationGenerationPrompt()
    PromptManager.register_prompt(narration_prompt, is_default=True)

    # 注册剧情上下文生成提示词
    plot_context_prompt = PlotContextGenerationPrompt()
    PromptManager.register_prompt(plot_context_prompt, is_default=True)


__all__ = [
    "FrameAnalysisPrompt",
    "NarrationGenerationPrompt",
    "PlotContextGenerationPrompt",
    "register_prompts"
]
