import os
import glob
import json
import time
import traceback
import asyncio
import streamlit as st
from loguru import logger

from app.config import config
from app.models.schema import VideoClipParams
from app.services.subtitle_text import decode_subtitle_bytes
from app.utils import utils, check_script
from webui.tools.generate_script_docu import generate_script_docu
from webui.tools.generate_script_short import generate_script_short
from webui.tools.generate_short_summary import generate_script_short_sunmmary


def render_script_panel(tr):
    """渲染脚本配置面板"""
    with st.container(border=True):
        st.write(tr("Video Script Configuration"))
        params = VideoClipParams()

        # 渲染脚本文件选择
        render_script_file(tr, params)

        # 渲染视频文件选择
        render_video_file(tr, params)

        # 获取当前选择的脚本类型
        script_path = st.session_state.get('video_clip_json_path', '')

        # 根据脚本类型显示不同的布局
        if script_path == "auto":
            # 画面解说
            render_video_details(tr)
        elif script_path == "short":
            # 短剧混剪
            render_short_generate_options(tr)
        elif script_path == "summary":
            # 短剧解说
            short_drama_summary(tr)
        else:
            # 默认为空
            pass

        # 渲染脚本操作按钮
        render_script_buttons(tr, params)


def render_script_file(tr, params):
    """渲染脚本文件选择"""
    # 定义功能模式
    MODE_FILE = "file_selection"
    MODE_AUTO = "auto"
    MODE_SHORT = "short"
    MODE_SUMMARY = "summary"

    # 处理保存脚本后的模式切换（必须在 widget 实例化之前）
    if st.session_state.get('_switch_to_file_mode'):
        st.session_state['script_mode_selection'] = tr("Select/Upload Script")
        del st.session_state['_switch_to_file_mode']

    # 模式选项映射
    mode_options = {
        tr("Select/Upload Script"): MODE_FILE,
        tr("Auto Generate"): MODE_AUTO,
        tr("Short Generate"): MODE_SHORT,
        tr("Short Drama Summary"): MODE_SUMMARY,
    }
    
    # 获取当前状态
    current_path = st.session_state.get('video_clip_json_path', '')
    
    # 确定当前选中的模式索引
    default_index = 0
    mode_keys = list(mode_options.keys())
    
    if current_path == "auto":
        default_index = mode_keys.index(tr("Auto Generate"))
    elif current_path == "short":
        default_index = mode_keys.index(tr("Short Generate"))
    elif current_path == "summary":
        default_index = mode_keys.index(tr("Short Drama Summary"))
    else:
        default_index = mode_keys.index(tr("Select/Upload Script"))

    # 1. 渲染功能选择下拉框
    # 使用 segmented_control 替代 selectbox，提供更好的视觉体验
    default_mode_label = mode_keys[default_index]
    
    # 定义回调函数来处理状态更新
    def update_script_mode():
        # 获取当前选中的标签
        selected_label = st.session_state.script_mode_selection
        if selected_label:
            # 更新实际的 path 状态
            new_mode = mode_options[selected_label]
            st.session_state.video_clip_json_path = new_mode
            params.video_clip_json_path = new_mode
        else:
            # 如果用户取消选择（segmented_control 允许取消），恢复到默认或上一个状态
            # 这里我们强制保持当前状态，或者重置为默认
            st.session_state.script_mode_selection = default_mode_label

    # 渲染组件
    selected_mode_label = st.segmented_control(
        tr("Video Type"),
        options=mode_keys,
        default=default_mode_label,
        key="script_mode_selection",
        on_change=update_script_mode
    )
    
    # 处理未选择的情况（虽然有default，但在某些交互下可能为空）
    if not selected_mode_label:
        selected_mode_label = default_mode_label
        
    selected_mode = mode_options[selected_mode_label]

    # 2. 根据选择的模式处理逻辑
    if selected_mode == MODE_FILE:
        # --- 文件选择模式 ---
        script_list = [
            (tr("None"), ""),
            (tr("Upload Script"), "upload_script")
        ]

        # 获取已有脚本文件
        suffix = "*.json"
        script_dir = utils.script_dir()
        files = glob.glob(os.path.join(script_dir, suffix))
        file_list = []

        for file in files:
            file_list.append({
                "name": os.path.basename(file),
                "file": file,
                "ctime": os.path.getctime(file)
            })

        file_list.sort(key=lambda x: x["ctime"], reverse=True)
        for file in file_list:
            display_name = file['file'].replace(config.root_dir, "")
            script_list.append((display_name, file['file']))

        # 找到保存的脚本文件在列表中的索引
        # 如果当前path是特殊值(auto/short/summary)，则重置为空
        saved_script_path = current_path if current_path not in [MODE_AUTO, MODE_SHORT, MODE_SUMMARY] else ""
        
        selected_index = 0
        for i, (_, path) in enumerate(script_list):
            if path == saved_script_path:
                selected_index = i
                break

        # 如果找到了保存的脚本，同步更新 selectbox 的 key 状态
        if saved_script_path and selected_index > 0:
            st.session_state['script_file_selection'] = selected_index

        selected_script_index = st.selectbox(
            tr("Script Files"),
            index=selected_index,
            options=range(len(script_list)),
            format_func=lambda x: script_list[x][0],
            key="script_file_selection"
        )

        script_path = script_list[selected_script_index][1]
        # 只有当用户实际选择了脚本时才更新路径，避免覆盖已保存的路径
        if script_path:
            st.session_state['video_clip_json_path'] = script_path
            params.video_clip_json_path = script_path
        elif saved_script_path:
            # 如果用户选择了 "None" 但之前有保存的脚本，保持原有路径
            st.session_state['video_clip_json_path'] = saved_script_path
            params.video_clip_json_path = saved_script_path

        # 处理脚本上传
        if script_path == "upload_script":
            uploaded_file = st.file_uploader(
                tr("Upload Script File"),
                type=["json"],
                accept_multiple_files=False,
            )

            if uploaded_file is not None:
                try:
                    # 读取上传的JSON内容并验证格式
                    script_content = uploaded_file.read().decode('utf-8')
                    json_data = json.loads(script_content)

                    # 保存到脚本目录
                    safe_filename = os.path.basename(uploaded_file.name)
                    script_file_path = os.path.join(script_dir, safe_filename)
                    file_name, file_extension = os.path.splitext(safe_filename)

                    # 如果文件已存在,添加时间戳
                    if os.path.exists(script_file_path):
                        timestamp = time.strftime("%Y%m%d%H%M%S")
                        file_name_with_timestamp = f"{file_name}_{timestamp}"
                        script_file_path = os.path.join(script_dir, file_name_with_timestamp + file_extension)

                    # 写入文件
                    with open(script_file_path, "w", encoding='utf-8') as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)

                    # 更新状态
                    st.success(tr("Script Uploaded Successfully"))
                    st.session_state['video_clip_json_path'] = script_file_path
                    params.video_clip_json_path = script_file_path
                    time.sleep(1)
                    st.rerun()

                except json.JSONDecodeError:
                    st.error(tr("Invalid JSON format"))
                except Exception as e:
                    st.error(f"{tr('Upload failed')}: {str(e)}")
    else:
        # --- 功能生成模式 ---
        st.session_state['video_clip_json_path'] = selected_mode
        params.video_clip_json_path = selected_mode


def render_video_file(tr, params):
    """渲染视频文件选择"""
    video_list = [(tr("None"), ""), (tr("Upload Local Files"), "upload_local")]

    # 获取已有视频文件
    for suffix in ["*.mp4", "*.mov", "*.avi", "*.mkv"]:
        video_files = glob.glob(os.path.join(utils.video_dir(), suffix))
        for file in video_files:
            display_name = file.replace(config.root_dir, "")
            video_list.append((display_name, file))

    selected_video_index = st.selectbox(
        tr("Video File"),
        index=0,
        options=range(len(video_list)),
        format_func=lambda x: video_list[x][0]
    )

    video_path = video_list[selected_video_index][1]
    st.session_state['video_origin_path'] = video_path
    params.video_origin_path = video_path

    if video_path == "upload_local":
        uploaded_file = st.file_uploader(
            tr("Upload Local Files"),
            type=["mp4", "mov", "avi", "flv", "mkv"],
            accept_multiple_files=False,
        )

        if uploaded_file is not None:
            safe_filename = os.path.basename(uploaded_file.name)
            video_file_path = os.path.join(utils.video_dir(), safe_filename)
            file_name, file_extension = os.path.splitext(safe_filename)

            if os.path.exists(video_file_path):
                timestamp = time.strftime("%Y%m%d%H%M%S")
                file_name_with_timestamp = f"{file_name}_{timestamp}"
                video_file_path = os.path.join(utils.video_dir(), file_name_with_timestamp + file_extension)

            with open(video_file_path, "wb") as f:
                f.write(uploaded_file.read())
                st.success(tr("File Uploaded Successfully"))
                st.session_state['video_origin_path'] = video_file_path
                params.video_origin_path = video_file_path
                time.sleep(1)
                st.rerun()


def render_short_generate_options(tr):
    """
    渲染Short Generate模式下的特殊选项
    在Short Generate模式下，替换原有的输入框为自定义片段选项
    """
    short_drama_summary(tr)
    # 显示自定义片段数量选择器
    custom_clips = st.number_input(
        tr("自定义片段"),
        min_value=1,
        max_value=20,
        value=st.session_state.get('custom_clips', 5),
        help=tr("设置需要生成的短视频片段数量"),
        key="custom_clips_input"
    )
    st.session_state['custom_clips'] = custom_clips


def render_video_details(tr):
    """画面解说 渲染视频主题和提示词"""
    video_theme = st.text_input(tr("Video Theme"))
    movie_title = st.text_input(
        tr("电影名称"),
        value=st.session_state.get("movie_title", ""),
        help=tr("用于生成剧情简介、时间轴和全局角色图谱的正式片名"),
        key="movie_title_input",
    )
    render_subtitle_upload_section(tr, uploader_key="auto_subtitle_file_uploader")
    known_characters = st.text_area(
        tr("已知角色介绍"),
        value=st.session_state.get("known_characters", ""),
        help=tr("可选：输入已知角色、身份、关系，辅助生成剧情理解上下文"),
        height=120,
        key="known_characters_input",
    )
    plot_context_prompt = st.text_area(
        tr("全局角色图谱提示词"),
        value=st.session_state.get("plot_context_prompt", get_default_plot_context_prompt()),
        help=tr("可编辑：用于根据SRT和角色介绍生成剧情简介、时间轴与全局角色图谱"),
        height=320,
        key="plot_context_prompt_input",
    )
    render_plot_context_actions(tr, video_theme, movie_title, known_characters, plot_context_prompt)
    custom_prompt = st.text_area(
        tr("Generation Prompt"),
        value=st.session_state.get('video_plot', ''),
        help=tr("Custom prompt for LLM, leave empty to use default prompt"),
        height=180
    )
    # 非短视频模式下显示原有的三个输入框
    input_cols = st.columns(2)

    with input_cols[0]:
        st.number_input(
            tr("Frame Interval (seconds)"),
            min_value=0,
            value=st.session_state.get('frame_interval_input', config.frames.get('frame_interval_input', 3)),
            help=tr("Frame Interval (seconds) (More keyframes consume more tokens)"),
            key="frame_interval_input"
        )

    with input_cols[1]:
        st.number_input(
            tr("Batch Size"),
            min_value=0,
            value=st.session_state.get('vision_batch_size', config.frames.get('vision_batch_size', 10)),
            help=tr("Batch Size (More keyframes consume more tokens)"),
            key="vision_batch_size"
        )
    st.session_state['video_theme'] = video_theme
    st.session_state['movie_title'] = movie_title
    st.session_state['known_characters'] = known_characters
    st.session_state['plot_context_prompt'] = plot_context_prompt
    st.session_state['custom_prompt'] = custom_prompt
    return video_theme, custom_prompt


def short_drama_summary(tr):
    """短剧解说 渲染视频主题和提示词"""
    render_subtitle_upload_section(tr, uploader_key="subtitle_file_uploader")

    # 名称输入框
    video_theme = st.text_input(tr("短剧名称"))
    st.session_state['video_theme'] = video_theme
    # 数字输入框
    temperature = st.slider("temperature", 0.0, 2.0, 0.7)
    st.session_state['temperature'] = temperature
    return video_theme


def render_subtitle_upload_section(tr, uploader_key: str = "subtitle_file_uploader"):
    """渲染通用字幕上传区域"""
    if 'subtitle_file_processed' not in st.session_state:
        st.session_state['subtitle_file_processed'] = False

    subtitle_file = st.file_uploader(
        tr("上传字幕文件"),
        type=["srt"],
        accept_multiple_files=False,
        key=uploader_key,
    )

    if 'subtitle_path' in st.session_state and st.session_state['subtitle_path']:
        st.info(f"已上传字幕: {os.path.basename(st.session_state['subtitle_path'])}")
        if st.button(tr("清除已上传字幕"), key=f"{uploader_key}_clear"):
            st.session_state['subtitle_path'] = None
            st.session_state['subtitle_content'] = None
            st.session_state['subtitle_file_processed'] = False
            st.session_state['plot_context_result'] = None
            st.session_state['plot_context_result_text'] = ""
            st.rerun()

    if subtitle_file is not None and not st.session_state['subtitle_file_processed']:
        try:
            safe_filename = os.path.basename(subtitle_file.name)
            decoded = decode_subtitle_bytes(subtitle_file.getvalue())
            script_content = decoded.text
            detected_encoding = decoded.encoding

            if not script_content:
                st.error(tr("无法读取字幕文件，请检查文件编码（支持 UTF-8、UTF-16、GBK、GB2312）"))
                st.stop()

            if len(script_content.strip()) < 10:
                st.warning(tr("字幕文件内容似乎为空，请检查文件"))

            script_file_path = os.path.join(utils.subtitle_dir(), safe_filename)
            file_name, file_extension = os.path.splitext(safe_filename)

            if os.path.exists(script_file_path):
                timestamp = time.strftime("%Y%m%d%H%M%S")
                file_name_with_timestamp = f"{file_name}_{timestamp}"
                script_file_path = os.path.join(utils.subtitle_dir(), file_name_with_timestamp + file_extension)

            with open(script_file_path, "w", encoding='utf-8') as f:
                f.write(script_content)

            st.success(
                f"{tr('字幕上传成功')} "
                f"(编码: {detected_encoding.upper()}, "
                f"大小: {len(script_content)} 字符)"
            )
            st.session_state['subtitle_path'] = script_file_path
            st.session_state['subtitle_content'] = script_content
            st.session_state['subtitle_file_processed'] = True
        except Exception as e:
            st.error(f"{tr('Upload failed')}: {str(e)}")


def render_plot_context_actions(
    tr,
    video_theme: str,
    movie_title: str,
    known_characters: str,
    plot_context_prompt: str,
):
    """渲染全局角色图谱生成按钮和结果区域"""
    plot_context_files = _list_plot_context_files()
    plot_context_options = [("未选择", "")] + [
        (f"{item['movie_title']} | {item['mtime']} | {item['name']}", item["path"]) for item in plot_context_files
    ]
    selected_saved_path = st.selectbox(
        tr("已保存剧情上下文"),
        options=[item[1] for item in plot_context_options],
        index=0,
        format_func=lambda value: next((label for label, path in plot_context_options if path == value), value or "未选择"),
        key="plot_context_saved_file_select",
    )
    if st.button(tr("加载已保存剧情上下文"), key="load_plot_context_btn", use_container_width=True):
        if not selected_saved_path:
            st.warning("请先选择已保存的剧情上下文文件")
        else:
            try:
                payload = _load_plot_context_from_file(selected_saved_path)
                _set_plot_context_state(payload)
                st.session_state["plot_context_file_path"] = selected_saved_path
                st.success(f"已加载剧情上下文: {selected_saved_path}")
            except ValueError as e:
                st.error(str(e))

    action_cols = st.columns(2)
    with action_cols[0]:
        generate_clicked = st.button(tr("生成全局角色图谱"), key="generate_plot_context_btn", use_container_width=True)
    with action_cols[1]:
        clear_clicked = st.button(tr("清空角色图谱结果"), key="clear_plot_context_btn", use_container_width=True)

    if clear_clicked:
        st.session_state["plot_context_result"] = None
        st.session_state["plot_context_result_text"] = ""
        st.session_state["plot_context_file_path"] = ""
        st.rerun()

    if generate_clicked:
        subtitle_content = st.session_state.get("subtitle_content", "")
        subtitle_path = st.session_state.get("subtitle_path", "")
        if not str(subtitle_content).strip() and not str(subtitle_path).strip():
            st.error("请先上传字幕文件")
            st.stop()
        if not str(movie_title).strip():
            st.error("请先输入电影名称")
            st.stop()

        from app.services.documentary.frame_analysis_service import DocumentaryFrameAnalysisService

        service = DocumentaryFrameAnalysisService()
        try:
            with st.spinner("正在生成全局角色图谱..."):
                result = asyncio.run(
                    service.generate_plot_context(
                        movie_title=movie_title,
                        video_theme=video_theme,
                        subtitle_content=subtitle_content,
                        subtitle_file_path=subtitle_path,
                        known_characters=known_characters,
                        plot_context_prompt=plot_context_prompt,
                    )
                )
            if not result:
                st.warning("未生成有效的全局角色图谱结果")
            else:
                _set_plot_context_state(result, sync_widget_values=True)
                st.session_state["plot_context_file_path"] = ""
                st.success("全局角色图谱生成成功")
        except Exception as e:
            logger.exception(f"生成全局角色图谱时发生错误\n{traceback.format_exc()}")
            st.error(f"生成全局角色图谱失败: {str(e)}")

    plot_context_result = st.session_state.get("plot_context_result")
    if plot_context_result:
        st.caption(f"当前结果文件: {st.session_state.get('plot_context_file_path', '未保存') or '未保存'}")

        movie_title = st.text_input(
            tr("电影名称"),
            value=st.session_state.get("plot_context_movie_title", plot_context_result.get("movie_title", "")),
            key="plot_context_movie_title",
        )
        plot_summary = st.text_area(
            tr("剧情简介"),
            value=st.session_state.get("plot_context_plot_summary", plot_context_result.get("plot_summary", "")),
            height=120,
            key="plot_context_plot_summary",
        )
        timeline_text = st.text_area(
            tr("时间轴"),
            value=st.session_state.get(
                "plot_context_timeline_text",
                json.dumps(plot_context_result.get("timeline", []), ensure_ascii=False, indent=2),
            ),
            height=220,
            key="plot_context_timeline_text",
        )
        characters_text = st.text_area(
            tr("角色图谱"),
            value=st.session_state.get(
                "plot_context_characters_text",
                json.dumps(plot_context_result.get("characters", []), ensure_ascii=False, indent=2),
            ),
            height=320,
            key="plot_context_characters_text",
        )

        save_cols = st.columns(2)
        with save_cols[0]:
            save_clicked = st.button(tr("保存剧情上下文"), key="save_plot_context_btn", use_container_width=True)
        with save_cols[1]:
            sync_clicked = st.button(tr("同步到当前结果"), key="sync_plot_context_btn", use_container_width=True)

        if sync_clicked or save_clicked:
            try:
                plot_context_payload = _build_plot_context_payload(
                    movie_title=movie_title,
                    plot_summary=plot_summary,
                    timeline_text=timeline_text,
                    characters_text=characters_text,
                )
                _set_plot_context_state(plot_context_payload, sync_widget_values=False)
                if save_clicked:
                    saved_file_path = _save_plot_context_to_file(plot_context_payload, movie_title or video_theme)
                    st.session_state["plot_context_file_path"] = saved_file_path
                    st.success(f"剧情上下文已保存: {saved_file_path}")
                else:
                    st.session_state["plot_context_file_path"] = ""
                    st.success("剧情上下文已同步到当前结果")
            except ValueError as e:
                st.error(str(e))

        with st.expander(tr("查看完整剧情上下文 JSON"), expanded=False):
            st.code(
                st.session_state.get("plot_context_result_text", json.dumps(plot_context_result, ensure_ascii=False, indent=2)),
                language="json",
            )


def _build_plot_context_payload(
    *,
    movie_title: str,
    plot_summary: str,
    timeline_text: str,
    characters_text: str,
) -> dict:
    movie_title = (movie_title or "").strip()
    if not movie_title:
        raise ValueError("电影名称不能为空")

    try:
        timeline = json.loads(timeline_text or "[]")
    except json.JSONDecodeError as e:
        raise ValueError(f"时间轴不是合法 JSON: {str(e)}") from e

    try:
        characters = json.loads(characters_text or "[]")
    except json.JSONDecodeError as e:
        raise ValueError(f"角色图谱不是合法 JSON: {str(e)}") from e

    if not isinstance(timeline, list):
        raise ValueError("时间轴必须是 JSON 数组")
    if not isinstance(characters, list):
        raise ValueError("角色图谱必须是 JSON 数组")

    return {
        "movie_title": movie_title,
        "plot_summary": (plot_summary or "").strip(),
        "timeline": timeline,
        "characters": characters,
    }


def _set_plot_context_state(payload: dict, sync_widget_values: bool = True):
    st.session_state["plot_context_result"] = payload
    st.session_state["plot_context_result_text"] = json.dumps(payload, ensure_ascii=False, indent=2)
    if sync_widget_values:
        st.session_state["plot_context_movie_title"] = payload.get("movie_title", "")
        st.session_state["plot_context_plot_summary"] = payload.get("plot_summary", "")
        st.session_state["plot_context_timeline_text"] = json.dumps(payload.get("timeline", []), ensure_ascii=False, indent=2)
        st.session_state["plot_context_characters_text"] = json.dumps(payload.get("characters", []), ensure_ascii=False, indent=2)


def _save_plot_context_to_file(payload: dict, video_theme: str) -> str:
    base_name = (video_theme or payload.get("movie_title", "") or "plot_context").strip()
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in base_name)[:80].strip("_")
    if not safe_name:
        safe_name = "plot_context"

    timestamp = time.strftime("%Y%m%d%H%M%S")
    file_path = os.path.join(utils.plot_context_dir(), f"{safe_name}_{timestamp}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return file_path


def _list_plot_context_files() -> list[dict]:
    files = []
    for name in os.listdir(utils.plot_context_dir()):
        if not name.endswith(".json"):
            continue
        path = os.path.join(utils.plot_context_dir(), name)
        if not os.path.isfile(path):
            continue
        movie_title = _read_plot_context_movie_title(path)
        files.append(
            {
                "name": name,
                "path": path,
                "movie_title": movie_title or "未命名电影",
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))),
            }
        )
    files.sort(key=lambda item: os.path.getmtime(item["path"]), reverse=True)
    return files


def _load_plot_context_from_file(file_path: str) -> dict:
    if not file_path or not os.path.exists(file_path):
        raise ValueError("剧情上下文文件不存在")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"剧情上下文文件不是合法 JSON: {str(e)}") from e

    if not isinstance(payload, dict):
        raise ValueError("剧情上下文文件内容必须是 JSON 对象")
    if "movie_title" not in payload or "timeline" not in payload or "characters" not in payload:
        raise ValueError("剧情上下文文件缺少必要字段")
    return payload


def _read_plot_context_movie_title(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return ""

    if not isinstance(payload, dict):
        return ""
    return str(payload.get("movie_title", "")).strip()


def get_default_plot_context_prompt() -> str:
    """获取自动生成全局剧情上下文的默认提示词"""
    return """# 角色设定
你是一位资深的剧本拆解师兼数据结构化专家。你的任务是根据零散的影视资料，构建一个严谨、完整且无歧义的【全局剧情上下文 JSON】。这个结构化结果将作为后续 AI 视频剪辑和解说词生成的唯一真理（Source of Truth）。

# 任务目标
我将为你提供一部影视作品的电影名称、关键角色介绍（可选）以及完整/部分 SRT 字幕。
你的任务是：
1. 生成一句到一段可复用的剧情简介，准确概括主线冲突、阶段目标和情绪基调。
2. 生成时间轴形式的剧情发展，按照字幕时间顺序梳理关键事件，突出转折、冲突升级、人物关系变化与结果。
3. 构建全局角色图谱：
   - 录入我提供的已知角色信息。
   - 从 SRT 中挖掘推动剧情的关键配角、反派和功能角色。
   - 将同一角色的不同叫法、职业称呼、代词指代、外号进行归一化，统一收录到 aliases 中。

# 分析步骤要求
1. 通读全局，理解整体故事脉络和阵营关系。
2. 提取所有对剧情发展有意义的人物实体。
3. 合并同类项，将指向同一角色的名字、职业、外号、关系称呼合并为一个独立 Character ID。
4. 梳理角色之间的基础关系、冲突方向、共同目标和敌对关系。
5. 所有判断必须尽量基于给定字幕与角色介绍；不确定时可保守概括，但不能胡编不存在的情节细节。

# 输出要求
你必须仅输出一个合法 JSON 对象，不包含 Markdown 代码块，不包含解释文字，不包含注释。
JSON 必须使用以下结构：
{
  "movie_title": "《电影名称》",
  "plot_summary": "剧情简介",
  "timeline": [
    {
      "start": "00:00:00,000",
      "end": "00:01:23,000",
      "event": "该时间段发生的关键剧情",
      "involved_characters": ["char_01", "char_02"],
      "relationship_change": "如无变化可为空字符串"
    }
  ],
  "characters": [
    {
      "id": "char_01",
      "is_protagonist": true,
      "primary_name": "张三",
      "aliases": ["张警官", "哥哥", "那个疯子", "男主"],
      "role_archetype": "落魄警察/复仇者",
      "core_motivation": "抓住当年杀害妻子的凶手",
      "visual_markers": ["总是穿着脏风衣", "右脸有刀疤"],
      "initial_relationships": {
        "char_02": "死敌/猎物",
        "char_03": "上司，经常产生冲突"
      }
    }
  ]
}

# 额外约束
1. movie_title 必须保留书名号格式。
2. timeline 必须按时间顺序输出，时间格式严格使用 SRT 风格 HH:MM:SS,mmm。
3. aliases 必须尽可能覆盖字幕中出现过的别称、称呼和职位称谓。
4. characters 至少包含主角与主要对立角色；如果字幕能识别更多关键人物，也要补齐。
5. 若已知角色介绍为空，仍需仅基于字幕尽最大可能构建结果。
6. 所有字段必须存在；缺失信息时用空字符串、空数组或空对象占位。"""


def render_script_buttons(tr, params):
    """渲染脚本操作按钮"""
    # 获取当前选择的脚本类型
    script_path = st.session_state.get('video_clip_json_path', '')

    # 生成/加载按钮
    if script_path == "auto":
        button_name = tr("Generate Video Script")
    elif script_path == "short":
        button_name = tr("Generate Short Video Script")
    elif script_path == "summary":
        button_name = tr("生成短剧解说脚本")
    elif script_path.endswith("json"):
        button_name = tr("Load Video Script")
    else:
        button_name = tr("Please Select Script File")

    if st.button(button_name, key="script_action", disabled=not script_path):
        if script_path == "auto":
            # 执行纪录片视频脚本生成（视频无字幕无配音）
            generate_script_docu(params)
        elif script_path == "short":
            # 执行 短剧混剪 脚本生成
            custom_clips = st.session_state.get('custom_clips')
            generate_script_short(tr, params, custom_clips)
        elif script_path == "summary":
            # 执行 短剧解说 脚本生成
            subtitle_path = st.session_state.get('subtitle_path')
            video_theme = st.session_state.get('video_theme')
            temperature = st.session_state.get('temperature')
            generate_script_short_sunmmary(params, subtitle_path, video_theme, temperature)
        else:
            load_script(tr, script_path)

    # 视频脚本编辑区
    video_clip_json_details = st.text_area(
        tr("Video Script"),
        value=json.dumps(st.session_state.get('video_clip_json', []), indent=2, ensure_ascii=False),
        height=500
    )

    # 操作按钮行 - 合并格式检查和保存功能
    if st.button(tr("Save Script"), key="save_script", use_container_width=True):
        save_script_with_validation(tr, video_clip_json_details)


def load_script(tr, script_path):
    """加载脚本文件"""
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()
            script = utils.clean_model_output(script)
            st.session_state['video_clip_json'] = json.loads(script)
            st.success(tr("Script loaded successfully"))
            st.rerun()
    except Exception as e:
        logger.error(f"加载脚本文件时发生错误\n{traceback.format_exc()}")
        st.error(f"{tr('Failed to load script')}: {str(e)}")


def save_script_with_validation(tr, video_clip_json_details):
    """保存视频脚本（包含格式验证）"""
    if not video_clip_json_details:
        st.error(tr("请输入视频脚本"))
        st.stop()

    # 第一步：格式验证
    with st.spinner("正在验证脚本格式..."):
        try:
            result = check_script.check_format(video_clip_json_details)
            if not result.get('success'):
                # 格式验证失败，显示详细错误信息
                error_message = result.get('message', '未知错误')
                error_details = result.get('details', '')

                st.error(f"**脚本格式验证失败**")
                st.error(f"**错误信息：** {error_message}")
                if error_details:
                    st.error(f"**详细说明：** {error_details}")

                # 显示正确格式示例
                st.info("**正确的脚本格式示例：**")
                example_script = [
                    {
                        "_id": 1,
                        "timestamp": "00:00:00,600-00:00:07,559",
                        "picture": "工地上，蔡晓艳奋力救人，场面混乱",
                        "narration": "灾后重建，工地上险象环生！泼辣女工蔡晓艳挺身而出，救人第一！",
                        "OST": 0
                    },
                    {
                        "_id": 2,
                        "timestamp": "00:00:08,240-00:00:12,359",
                        "picture": "领导视察，蔡晓艳不屑一顾",
                        "narration": "播放原片4",
                        "OST": 1
                    }
                ]
                st.code(json.dumps(example_script, ensure_ascii=False, indent=2), language='json')
                st.stop()

        except Exception as e:
            st.error(f"格式验证过程中发生错误: {str(e)}")
            st.stop()

    # 第二步：保存脚本
    with st.spinner(tr("Save Script")):
        script_dir = utils.script_dir()
        timestamp = time.strftime("%Y-%m%d-%H%M%S")
        save_path = os.path.join(script_dir, f"{timestamp}.json")

        try:
            data = json.loads(video_clip_json_details)
            with open(save_path, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
                st.session_state['video_clip_json'] = data
                st.session_state['video_clip_json_path'] = save_path
                
                # 标记需要切换到文件选择模式（在下次渲染前处理）
                st.session_state['_switch_to_file_mode'] = True

                # 更新配置
                config.app["video_clip_json_path"] = save_path

                # 显示成功消息
                st.success("✅ 脚本格式验证通过，保存成功！")

                # 强制重新加载页面更新选择框
                time.sleep(0.5)  # 给一点时间让用户看到成功消息
                st.rerun()

        except Exception as err:
            st.error(f"{tr('Failed to save script')}: {str(err)}")
            st.stop()


# crop_video函数已移除 - 现在使用统一裁剪策略，不再需要预裁剪步骤


def get_script_params():
    """获取脚本参数"""
    return {
        'video_language': st.session_state.get('video_language', ''),
        'video_clip_json_path': st.session_state.get('video_clip_json_path', ''),
        'video_origin_path': st.session_state.get('video_origin_path', ''),
        'video_name': st.session_state.get('video_name', ''),
        'video_plot': st.session_state.get('video_plot', '')
    }
