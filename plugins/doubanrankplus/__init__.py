import os
import re
import shutil
from pathlib import Path
from typing import Any, List, Dict, Tuple

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType

class ForceManualTransfer(_PluginBase):
    # 插件名称
    plugin_name = "强制手动整理(免TMDB)"
    # 插件描述
    plugin_desc = "无需经过TMDB识别，直接根据配置的名称和季号，强制批量重命名并整理到目标媒体库。"
    # 插件图标
    plugin_icon = "edit"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "神医定制"
    # 插件配置项ID前缀
    plugin_config_prefix = "force_transfer_"
    # 加载顺序
    plugin_order = 30
    # 可使用的用户级别
    auth_level = 1

    _enabled = False
    _run_now = False
    _source_path = ""
    _target_path = ""
    _media_name = ""
    _season = 1
    _transfer_type = "softlink"
    
    # 支持强制整理的扩展名（包含你的 strm）
    _exts = ['.strm', '.mp4', '.mkv', '.ts', '.avi', '.rmvb', '.wmv', '.mov', '.flv', '.ass', '.srt', '.nfo']

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._run_now = config.get("run_now")
            self._source_path = config.get("source_path")
            self._target_path = config.get("target_path")
            self._media_name = config.get("media_name")
            self._season = config.get("season", 1)
            self._transfer_type = config.get("transfer_type", "softlink")

            # 如果开启了“立即运行”，则执行任务
            if self._enabled and self._run_now:
                logger.info(f"触发强制手动整理任务：{self._media_name}")
                self._do_transfer()
                # 任务执行完后，自动把界面的开关拨回 False，防止循环执行
                config["run_now"] = False
                self.update_config(config)

    def _get_episode(self, filename):
        """智能提取文件名中的集数"""
        # 1. 优先匹配 S01E01, EP01, 第1集, E01 这种明确的集数
        match = re.search(r'(?i)(?:e|ep|第)\s*(\d+)', filename)
        if match:
            return int(match.group(1))
        # 2. 如果没有明确标志，提取文件名里出现的最后一段数字（过滤掉分辨率）
        numbers = re.findall(r'(\d+)', filename)
        valid_nums = [int(n) for n in numbers if int(n) < 1000 and int(n) not in [264, 265, 720, 480]]
        if valid_nums:
            return valid_nums[-1]
        return None

    def _do_transfer(self):
        if not self._source_path or not self._target_path or not self._media_name:
            logger.error("【强制整理】源目录、目标目录或媒体名称为空，无法整理")
            return

        src_dir = Path(self._source_path)
        if not src_dir.exists() or not src_dir.is_dir():
            logger.error(f"【强制整理】源目录不存在：{src_dir}")
            return

        try:
            season_num = int(self._season)
        except:
            season_num = 1

        # 按照 Emby 完美识别标准创建目标目录结构
        target_dir = Path(self._target_path) / self._media_name / f"Season {season_num}"
        target_dir.mkdir(parents=True, exist_ok=True)

        success_count = 0
        files = [f for f in src_dir.iterdir() if f.is_file() and f.suffix.lower() in self._exts]
        
        # 兜底机制：如果没提取到集数，按字母顺序强行编号
        files.sort(key=lambda x: x.name)
        fallback_ep = 1

        for file in files:
            ep = self._get_episode(file.stem)
            if ep is None:
                ep = fallback_ep
                fallback_ep += 1
            
            ext = file.suffix.lower()
            # 拼接成 Emby 最喜欢的格式
            new_filename = f"{self._media_name} - S{season_num:02d}E{ep:02d}{ext}"
            new_filepath = target_dir / new_filename

            if new_filepath.exists():
                new_filepath.unlink() # 如果目标位置已有同名文件，先删除防止冲突

            try:
                if self._transfer_type == "move":
                    shutil.move(str(file), str(new_filepath))
                elif self._transfer_type == "copy":
                    shutil.copy2(str(file), str(new_filepath))
                elif self._transfer_type == "link":
                    os.link(str(file), str(new_filepath))
                elif self._transfer_type == "softlink":
                    os.symlink(str(file), str(new_filepath))
                
                logger.info(f"【强制整理】{file.name} -> {new_filename}")
                success_count += 1
            except Exception as e:
                logger.error(f"【强制整理】处理文件 {file.name} 失败: {e}")

        # 发送处理完成通知
        msg = f"剧集: {self._media_name}\n共处理: {success_count} 个文件\n方式: {self._transfer_type}"
        self.post_message(mtype=NotificationType.Manual, title="强制整理成功", text=msg)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件'}}]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{'component': 'VSwitch', 'props': {'model': 'run_now', 'label': '立即运行 (执行完毕开关会自动回弹关闭)'}}]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{'component': 'VTextField', 'props': {'model': 'source_path', 'label': '源目录绝对路径 (如: /volume1/Symlink/video/未知猪猪侠)', 'required': True}}]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{'component': 'VTextField', 'props': {'model': 'target_path', 'label': '目标媒体库大目录 (如: /volume1/Symlink/link/儿童剧集)', 'required': True}}]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{'component': 'VTextField', 'props': {'model': 'media_name', 'label': '最终剧集名称 (如: 猪猪侠之南海日记)', 'required': True}}]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{'component': 'VTextField', 'props': {'model': 'season', 'label': '属于第几季 (填数字)', 'placeholder': '1', 'required': True}}]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'transfer_type',
                                            'label': '你要怎么整理？',
                                            'items': [
                                                {'title': '创建软链接 (Softlink)', 'value': 'softlink'},
                                                {'title': '创建硬链接 (Link)', 'value': 'link'},
                                                {'title': '复制过去 (Copy)', 'value': 'copy'},
                                                {'title': '移动过去 (Move)', 'value': 'move'}
                                            ],
                                            'required': True
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "run_now": False,
            "source_path": "",
            "target_path": "",
            "media_name": "",
            "season": "1",
            "transfer_type": "softlink"
        }

    def get_page(self) -> List[dict]:
        return []

    def stop_service(self):
        pass
