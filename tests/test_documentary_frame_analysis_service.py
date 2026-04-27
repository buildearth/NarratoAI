import unittest
import os
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from app.services.documentary.frame_analysis_models import DocumentaryAnalysisConfig
from app.services.documentary.frame_analysis_service import DocumentaryFrameAnalysisService
from app.utils import utils


class DocumentaryFrameAnalysisServiceTests(unittest.TestCase):
    def test_build_analysis_prompt_formats_real_frame_count(self):
        service = DocumentaryFrameAnalysisService()

        prompt = service._build_analysis_prompt(frame_count=3)

        self.assertIn("我提供了 3 张视频帧", prompt)
        self.assertNotIn("%s", prompt)
        self.assertIn("frame_observations", prompt)
        self.assertIn("overall_activity_summary", prompt)

    def test_parse_failed_batch_keeps_raw_response_and_time_range(self):
        service = DocumentaryFrameAnalysisService()

        batch = service._build_failed_batch_result(
            batch_index=2,
            raw_response="not-json",
            error_message="JSON decode failed",
            frame_paths=["/tmp/keyframe_000000_000000000.jpg"],
            time_range="00:00:00,000-00:00:03,000",
        )

        self.assertEqual("failed", batch.status)
        self.assertEqual("not-json", batch.raw_response)
        self.assertEqual("00:00:00,000-00:00:03,000", batch.time_range)
        self.assertTrue(batch.fallback_summary)

    def test_parse_failed_batch_uses_non_empty_fallback_when_raw_response_is_empty(self):
        service = DocumentaryFrameAnalysisService()

        batch = service._build_failed_batch_result(
            batch_index=3,
            raw_response="",
            error_message="Empty model response",
            frame_paths=["/tmp/keyframe_000001_000001000.jpg"],
            time_range="00:00:03,000-00:00:06,000",
        )

        self.assertEqual("failed", batch.status)
        self.assertEqual("", batch.raw_response)
        self.assertTrue(batch.fallback_summary)

    def test_failed_batch_result_uses_prompt_contract_field_names(self):
        service = DocumentaryFrameAnalysisService()

        batch = service._build_failed_batch_result(
            batch_index=4,
            raw_response="not-json",
            error_message="JSON decode failed",
            frame_paths=["/tmp/keyframe_000002_000002000.jpg"],
            time_range="00:00:06,000-00:00:09,000",
        )

        self.assertEqual([], batch.frame_observations)
        self.assertEqual("", batch.overall_activity_summary)
        self.assertFalse(hasattr(batch, "observations"))
        self.assertFalse(hasattr(batch, "summary"))

    def test_parse_batch_returns_failed_result_when_json_is_invalid(self):
        service = DocumentaryFrameAnalysisService()

        batch = service._parse_batch_response(
            batch_index=0,
            raw_response="plain text",
            frame_paths=["/tmp/keyframe_000000_000000000.jpg"],
            time_range="00:00:00,000-00:00:03,000",
        )

        self.assertEqual("failed", batch.status)
        self.assertEqual("plain text", batch.raw_response)
        self.assertEqual(["/tmp/keyframe_000000_000000000.jpg"], batch.frame_paths)
        self.assertEqual([], batch.frame_observations)
        self.assertEqual("", batch.overall_activity_summary)

    def test_parse_batch_returns_failed_result_for_empty_json_object(self):
        service = DocumentaryFrameAnalysisService()

        batch = service._parse_batch_response(
            batch_index=0,
            raw_response="{}",
            frame_paths=["/tmp/keyframe_000000_000000000.jpg"],
            time_range="00:00:00,000-00:00:03,000",
        )

        self.assertEqual("failed", batch.status)
        self.assertEqual("{}", batch.raw_response)
        self.assertIn("frame_observations", batch.error_message)

    def test_parse_batch_returns_failed_result_when_observations_are_too_short(self):
        service = DocumentaryFrameAnalysisService()
        raw_response = """
{
  "frame_observations": [
    {"observation": "第一帧画面"}
  ],
  "overall_activity_summary": "只有一条帧观察"
}
""".strip()

        batch = service._parse_batch_response(
            batch_index=1,
            raw_response=raw_response,
            frame_paths=[
                "/tmp/keyframe_000000_000000000.jpg",
                "/tmp/keyframe_000075_000003000.jpg",
            ],
            time_range="00:00:00,000-00:00:06,000",
        )

        self.assertEqual("failed", batch.status)
        self.assertEqual(raw_response, batch.raw_response)
        self.assertIn("frame_observations", batch.error_message)

    def test_parse_batch_parses_code_fenced_json_into_structured_result(self):
        service = DocumentaryFrameAnalysisService()
        raw_response = """```json
{
  "frame_observations": [
    {"observation": "第一帧画面"},
    {"observation": "第二帧画面"}
  ],
  "overall_activity_summary": "人物从房间走到街道"
}
```"""

        batch = service._parse_batch_response(
            batch_index=1,
            raw_response=raw_response,
            frame_paths=[
                "/tmp/keyframe_000000_000000000.jpg",
                "/tmp/keyframe_000075_000003000.jpg",
            ],
            time_range="00:00:00,000-00:00:06,000",
        )

        self.assertEqual("success", batch.status)
        self.assertEqual(
            [
                {
                    "frame_path": "/tmp/keyframe_000000_000000000.jpg",
                    "timestamp": "",
                    "observation": "第一帧画面",
                },
                {
                    "frame_path": "/tmp/keyframe_000075_000003000.jpg",
                    "timestamp": "",
                    "observation": "第二帧画面",
                },
            ],
            batch.frame_observations,
        )
        self.assertEqual("人物从房间走到街道", batch.overall_activity_summary)
        self.assertEqual("", batch.fallback_summary)

    def test_parse_batch_preserves_frames_when_summary_is_missing(self):
        service = DocumentaryFrameAnalysisService()
        raw_response = """
{
  "frame_observations": [
    {"observation": "第一帧画面"},
    {"observation": "第二帧画面"}
  ]
}
""".strip()

        batch = service._parse_batch_response(
            batch_index=2,
            raw_response=raw_response,
            frame_paths=[
                "/tmp/keyframe_000000_000000000.jpg",
                "/tmp/keyframe_000075_000003000.jpg",
            ],
            time_range="00:00:00,000-00:00:06,000",
        )

        self.assertEqual("success", batch.status)
        self.assertEqual(2, len(batch.frame_observations))
        self.assertEqual("", batch.overall_activity_summary)

    def test_cache_key_changes_when_interval_changes(self):
        service = DocumentaryFrameAnalysisService()

        with patch("app.services.documentary.frame_analysis_service.os.path.getmtime", return_value=100.0):
            key_a = service._build_cache_key("video.mp4", 3.0, "prompt-v1", "model-a", 10, 2)
            key_b = service._build_cache_key("video.mp4", 5.0, "prompt-v1", "model-a", 10, 2)

        self.assertNotEqual(key_a, key_b)

    def test_cache_key_changes_when_model_changes(self):
        service = DocumentaryFrameAnalysisService()

        with patch("app.services.documentary.frame_analysis_service.os.path.getmtime", return_value=100.0):
            key_a = service._build_cache_key("video.mp4", 3.0, "prompt-v1", "model-a", 10, 2)
            key_b = service._build_cache_key("video.mp4", 3.0, "prompt-v1", "model-b", 10, 2)

        self.assertNotEqual(key_a, key_b)

    def test_cache_key_starts_with_legacy_video_hash_prefix(self):
        service = DocumentaryFrameAnalysisService()

        with patch("app.services.documentary.frame_analysis_service.os.path.getmtime", return_value=123.0):
            key = service._build_cache_key("video.mp4", 3.0, "prompt-v1", "model-a", 10, 2)

        expected_prefix = utils.md5("video.mp4" + "123.0")
        self.assertTrue(key.startswith(expected_prefix))

    def test_build_narration_input_includes_plot_context_block(self):
        service = DocumentaryFrameAnalysisService()

        narration_input = service._build_narration_input(
            markdown_output="## 片段 1\n- 时间范围：00:00:00,000-00:00:03,000",
            video_theme="测试影片",
            custom_prompt="强调悬念",
            plot_context={
                "movie_title": "《测试影片》",
                "plot_summary": "一名男人深夜回家时发现异常。",
                "timeline": [
                    {
                        "start": "00:00:00,000",
                        "end": "00:00:10,000",
                        "event": "男人回家",
                        "involved_characters": ["char_01"],
                        "relationship_change": "",
                    }
                ],
                "characters": [
                    {
                        "id": "char_01",
                        "primary_name": "张三",
                        "aliases": ["男人"],
                        "role_archetype": "普通人",
                        "core_motivation": "查明真相",
                        "initial_relationships": {},
                    }
                ],
            },
        )

        self.assertIn("## 剧情上下文", narration_input)
        self.assertIn("剧情简介：一名男人深夜回家时发现异常。", narration_input)
        self.assertIn("角色图谱", narration_input)

    def test_format_plot_context_for_prompt_returns_json_string(self):
        service = DocumentaryFrameAnalysisService()
        plot_context = {"movie_title": "《测试影片》", "plot_summary": "简介", "timeline": [], "characters": []}

        result = service._format_plot_context_for_prompt(plot_context)

        self.assertIn('"movie_title": "《测试影片》"', result)
        self.assertIn('"plot_summary": "简介"', result)

    def test_clear_keyframes_cache_respects_scope_and_prefix_match(self):
        with TemporaryDirectory() as temp_root:
            service = DocumentaryFrameAnalysisService()
            analysis_dir = os.path.join(temp_root, "analysis")
            os.makedirs(analysis_dir, exist_ok=True)

            with patch("app.services.documentary.frame_analysis_service.os.path.getmtime", return_value=123.0):
                target_key_a = service._build_cache_key("video.mp4", 3.0, "prompt-v1", "model-a", 10, 2)
                target_key_b = service._build_cache_key("video.mp4", 5.0, "prompt-v1", "model-a", 10, 2)
                keep_key = service._build_cache_key("other.mp4", 3.0, "prompt-v1", "model-a", 10, 2)

            target_dir_a = os.path.join(analysis_dir, target_key_a)
            target_dir_b = os.path.join(analysis_dir, target_key_b)
            keep_dir = os.path.join(analysis_dir, keep_key)
            os.makedirs(target_dir_a, exist_ok=True)
            os.makedirs(target_dir_b, exist_ok=True)
            os.makedirs(keep_dir, exist_ok=True)

            with patch("app.utils.utils.temp_dir", return_value=temp_root), patch(
                "app.utils.utils.os.path.getmtime", return_value=123.0
            ):
                utils.clear_keyframes_cache(video_path="video.mp4", cache_scope="analysis")

            self.assertFalse(os.path.exists(target_dir_a))
            self.assertFalse(os.path.exists(target_dir_b))
            self.assertTrue(os.path.exists(keep_dir))


class DocumentaryAnalysisConfigTests(unittest.TestCase):
    def test_config_rejects_non_positive_frame_interval(self):
        with self.assertRaises(ValueError):
            DocumentaryAnalysisConfig(
                video_path="/tmp/demo.mp4",
                frame_interval_seconds=0,
                vision_batch_size=5,
                vision_llm_provider="openai",
                vision_model_name="gpt-4o-mini",
            )

    def test_config_rejects_non_positive_batch_size(self):
        with self.assertRaises(ValueError):
            DocumentaryAnalysisConfig(
                video_path="/tmp/demo.mp4",
                frame_interval_seconds=5,
                vision_batch_size=0,
                vision_llm_provider="openai",
                vision_model_name="gpt-4o-mini",
            )

    def test_config_rejects_non_positive_max_concurrency(self):
        with self.assertRaises(ValueError):
            DocumentaryAnalysisConfig(
                video_path="/tmp/demo.mp4",
                frame_interval_seconds=5,
                vision_batch_size=5,
                vision_llm_provider="openai",
                vision_model_name="gpt-4o-mini",
                max_concurrency=0,
            )


class DocumentaryPlotContextGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_maybe_generate_plot_context_returns_none_without_subtitle(self):
        service = DocumentaryFrameAnalysisService()

        result = await service._maybe_generate_plot_context(
            movie_title="《测试影片》",
            video_theme="测试影片",
            subtitle_content="",
            subtitle_file_path="",
            known_characters="",
            plot_context_prompt="",
            progress_callback=lambda _p, _m: None,
        )

        self.assertIsNone(result)

    async def test_maybe_generate_plot_context_builds_structured_result(self):
        service = DocumentaryFrameAnalysisService()
        llm_output = '{"movie_title":"《测试影片》","plot_summary":"简介","timeline":[],"characters":[]}'

        with patch.dict(
            "app.services.documentary.frame_analysis_service.config.app",
            {
                "text_llm_provider": "openai",
                "text_openai_api_key": "test-key",
                "text_openai_model_name": "test-model",
                "text_openai_base_url": "https://example.com/v1",
            },
        ), patch(
            "app.services.documentary.frame_analysis_service.UnifiedLLMService.generate_text",
            AsyncMock(return_value=llm_output),
        ) as mocked_generate:
            result = await service._maybe_generate_plot_context(
                movie_title="《测试影片》",
                video_theme="测试影片",
                subtitle_content="1\n00:00:00,000 --> 00:00:02,000\n你好\n",
                subtitle_file_path="",
                known_characters="张三：男主",
                plot_context_prompt="默认提示词",
                progress_callback=lambda _p, _m: None,
            )

        self.assertEqual("《测试影片》", result["movie_title"])
        self.assertEqual("简介", result["plot_summary"])
        self.assertEqual("openai", mocked_generate.call_args.kwargs["provider"])

    async def test_generate_plot_context_prefers_explicit_movie_title_over_video_theme(self):
        service = DocumentaryFrameAnalysisService()
        llm_output = '{"movie_title":"《显式片名》","plot_summary":"简介","timeline":[],"characters":[]}'

        with patch.dict(
            "app.services.documentary.frame_analysis_service.config.app",
            {
                "text_llm_provider": "openai",
                "text_openai_api_key": "test-key",
                "text_openai_model_name": "test-model",
                "text_openai_base_url": "https://example.com/v1",
            },
        ), patch(
            "app.services.documentary.frame_analysis_service.PromptManager.get_prompt",
            return_value="prompt",
        ) as mocked_prompt, patch(
            "app.services.documentary.frame_analysis_service.UnifiedLLMService.generate_text",
            AsyncMock(return_value=llm_output),
        ):
            await service.generate_plot_context(
                movie_title="显式片名",
                video_theme="主题名",
                subtitle_content="1\n00:00:00,000 --> 00:00:02,000\n你好\n",
                known_characters="",
                plot_context_prompt="默认提示词",
            )

        self.assertEqual("《显式片名》", mocked_prompt.call_args.kwargs["parameters"]["movie_title"])
