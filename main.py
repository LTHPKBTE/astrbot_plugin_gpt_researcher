from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.core.message.components import File, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_type import MessageType
import asyncio
import time
import re
import sys
import os
import tempfile
import uuid
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

# 导入自定义客户端
from .gptr_client import GPTResearcherClient, ResearchRequest, ReportType, ReportSource, Tone, ResearchResult


class ReportFormat(Enum):
    """报告格式枚举（保留但不再使用HTML转换）"""
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"


@dataclass
class ResearchTask:
    """研究任务信息"""
    task_id: str
    event: AstrMessageEvent
    query: str
    start_time: float
    last_progress_report_time: float = 0
    last_progress_percent: int = 0
    completed: bool = False
    result: Optional[ResearchResult] = None  # 改为 ResearchResult 类型
    error: Optional[str] = None


@register("astrbot_plugin_gpt_researcher", "Java8ver64", "为 AstrBot 添加 gpt-researcher 深度搜索支持", "0.2.0")
class GPTResearcherPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.research_tasks: Dict[str, ResearchTask] = {}
        self.active_tasks: Set[str] = set()
        
        # 从配置中加载参数
        self.trigger_keywords = self.config.get("trigger_keywords", ["研究", "deepresearch"])
        self.enable_keyword_trigger = self.config.get("enable_keyword_trigger", False)
        self.command_name = self.config.get("command_name", "research")
        self.report_format = self.config.get("report_format", "pdf")  # 默认改为pdf
        self.progress_frequency = self.config.get("progress_report_frequency", 10)
        self.progress_min_interval = self.config.get("progress_report_min_interval_seconds", 60)
        self.deep_research_enabled = self.config.get("deep_research_enabled", True)
        self.max_research_time = self.config.get("max_research_time_minutes", 30) * 60  # 转换为秒
        self.gpt_researcher_url = self.config.get("gpt_researcher_url", "http://localhost:8000")
        self.gpt_researcher_config = self.config.get("gpt_researcher_config", {})
        self.whitelist_enabled = self.config.get("whitelist_enabled", False)
        self.whitelist = self.config.get("whitelist", [])
        self.friend_only = self.config.get("friend_only", False)
        # 强制只发送文件，放弃文本消息
        self.send_as_file = True
        
        logger.info(f"GPT-Researcher 插件初始化完成，触发关键词: {self.trigger_keywords}")
        logger.info(f"关键词触发启用: {self.enable_keyword_trigger}, 命令触发: /{self.command_name}")
        logger.info(f"报告格式: {self.report_format}, 进度回报频率: {self.progress_frequency}%")
        logger.info(f"最小回报间隔: {self.progress_min_interval}秒, 最大研究时间: {self.max_research_time}秒")
        logger.info(f"白名单检查: {self.whitelist_enabled}, 好友限制: {self.friend_only}")
        logger.info(f"GPT-Researcher 服务地址: {self.gpt_researcher_url}")

    async def initialize(self):
        """插件初始化，验证gpt-researcher服务"""
        try:
            # 使用客户端检查服务健康状态
            async with GPTResearcherClient(base_url=self.gpt_researcher_url) as client:
                if await client.health_check():
                    logger.info("GPT-Researcher 服务连接成功")
                else:
                    logger.warning("GPT-Researcher 服务不可用，请确保服务正在运行")
        except Exception as e:
            logger.error(f"连接 GPT-Researcher 服务时发生错误: {e}")
            logger.error(f"请确保 gpt-researcher 后端服务正在运行，地址: {self.gpt_researcher_url}")

    async def terminate(self):
        """插件销毁，清理所有研究任务"""
        logger.info("GPT-Researcher 插件正在终止，清理研究任务...")
        # 取消所有正在运行的任务
        for task_id in list(self.active_tasks):
            await self.cancel_research_task(task_id)
        logger.info("GPT-Researcher 插件已终止")

    @filter.on_message()
    async def handle_message(self, event: AstrMessageEvent):
        """处理所有消息，检测触发关键词（仅在启用关键词触发时生效）"""
        if not self.enable_keyword_trigger:
            return
        
        message = event.message_str.strip()
        if not message:
            return

        # 检查消息是否包含触发关键词
        triggered, keyword = self._check_trigger_keywords(message)
        if not triggered:
            return

        # 权限检查：好友限制、白名单等
        permission_ok, reason = self._check_permission(event)
        if not permission_ok:
            logger.info(f"研究请求被拒绝: {reason}")
            yield event.plain_result(f"研究请求被拒绝: {reason}")
            return

        # 提取研究主题（去除关键词后的内容）
        query = self._extract_research_query(message, keyword)
        if not query:
            yield event.plain_result(f"请提供研究主题，例如：'{keyword} 人工智能的最新发展'")
            return

        # 发送确认消息
        yield event.plain_result(f"接受研究请求，关键词: {keyword}\n主题: {query}")

        # 启动研究任务
        await self.start_research_task(event, query)

    def _check_trigger_keywords(self, message: str) -> (bool, str):
        """检查消息是否包含触发关键词"""
        message_lower = message.lower()
        for keyword in self.trigger_keywords:
            if keyword.lower() in message_lower:
                return True, keyword
        return False, ""

    def _extract_research_query(self, message: str, keyword: str) -> str:
        """提取研究主题"""
        # 找到关键词位置，提取后面的内容
        idx = message.lower().find(keyword.lower())
        if idx == -1:
            return ""
        
        # 提取关键词后的内容
        query_start = idx + len(keyword)
        query = message[query_start:].strip()
        
        # 如果查询为空，尝试提取整个消息（去除关键词）
        if not query:
            # 尝试提取消息中除了关键词以外的部分
            parts = message.split()
            query_parts = [p for p in parts if p.lower() != keyword.lower()]
            query = " ".join(query_parts)
        
        return query

    def _check_permission(self, event: AstrMessageEvent) -> (bool, str):
        """检查用户权限：好友限制、白名单等"""
        # 好友限制检查
        if self.friend_only:
            if event.get_message_type() != MessageType.FRIEND_MESSAGE:
                return False, "仅限好友私聊触发研究任务"
        
        # 白名单检查
        if self.whitelist_enabled and self.whitelist:
            sender_id = event.get_sender_id()
            unified_msg_origin = event.unified_msg_origin
            # 检查是否在白名单中（支持简单ID或完整UMO）
            in_whitelist = False
            for item in self.whitelist:
                if item == sender_id or item == unified_msg_origin:
                    in_whitelist = True
                    break
                # 检查群组ID
                group_id = event.get_group_id()
                if group_id and item == group_id:
                    in_whitelist = True
                    break
            if not in_whitelist:
                return False, "您不在研究任务白名单中"
        
        return True, ""

    async def start_research_task(self, event: AstrMessageEvent, query: str):
        """启动研究任务"""
        task_id = str(uuid.uuid4())[:8]
        
        # 创建研究任务
        task = ResearchTask(
            task_id=task_id,
            event=event,
            query=query,
            start_time=time.time()
        )
        self.research_tasks[task_id] = task
        self.active_tasks.add(task_id)
        
        # 发送确认消息
        await event.reply(f"研究请求接收，关键词: {query[:50]}...")
        
        # 启动异步研究任务
        asyncio.create_task(self._execute_research_task(task))
        
        logger.info(f"研究任务 {task_id} 已启动，查询: {query}")

    async def _execute_research_task(self, task: ResearchTask):
        """执行研究任务 - 使用 HTTP 客户端"""
        try:
            # 创建客户端
            async with GPTResearcherClient(base_url=self.gpt_researcher_url, timeout=self.max_research_time) as client:
                # 准备研究请求
                request = ResearchRequest(
                    task=task.query,
                    report_type=ReportType.DEEP.value if self.deep_research_enabled else ReportType.RESEARCH_REPORT.value,
                    report_source=ReportSource.WEB.value,
                    tone=Tone.OBJECTIVE.value,
                    generate_in_background=False  # 同步执行，等待结果
                )
                
                # 发送进度报告
                await self._send_progress_report(task, 10)
                
                # 生成报告
                result = await client.generate_report(request)
                
                if result.error:
                    raise Exception(f"研究任务失败: {result.error}")
                
                # 更新任务状态
                task.completed = True
                task.result = result
                
                # 发送进度报告
                await self._send_progress_report(task, 100)
                
                # 发送最终报告（文件）
                await self._send_final_report(task)
                
        except asyncio.TimeoutError:
            error_msg = f"研究任务超时（{self.max_research_time}秒）"
            logger.warning(error_msg)
            task.error = error_msg
            await self._send_error_report(task, error_msg)
            
        except Exception as e:
            error_msg = f"研究任务执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            task.error = error_msg
            await self._send_error_report(task, error_msg)
            
        finally:
            # 清理任务
            self.active_tasks.discard(task.task_id)
            logger.info(f"研究任务 {task.task_id} 已完成")

    async def _send_progress_report(self, task: ResearchTask, percent: int):
        """发送进度报告"""
        try:
            # 避免频繁发送进度报告
            now = time.time()
            if percent < 100 and (now - task.last_progress_report_time < self.progress_min_interval):
                return
                
            message = f"研究进度: {percent}% \n主题: {task.query[:50]}..."
            if percent >= 100:
                message = "研究完成，正在撰写报告文件，这可能需要十分钟..."
            
            await task.event.reply(message)
            task.last_progress_report_time = now
            task.last_progress_percent = percent
            logger.info(f"研究任务 {task.task_id} 进度报告: {percent}%")
        except Exception as e:
            logger.error(f"发送进度报告失败: {e}")

    async def _send_final_report(self, task: ResearchTask):
        """发送最终报告 - 只发送文件，不发送文本"""
        try:
            if not task.result or not task.result.research_id:
                raise ValueError("研究结果为空")
            
            result = task.result
            
            # 根据配置的格式选择要发送的文件
            file_path = None
            file_ext = ""
            
            if self.report_format == ReportFormat.PDF.value and result.pdf_path:
                file_path = result.pdf_path
                file_ext = "pdf"
            elif self.report_format == ReportFormat.DOCX.value and result.docx_path:
                file_path = result.docx_path
                file_ext = "docx"
            elif result.docx_path:  # 默认使用docx
                file_path = result.docx_path
                file_ext = "docx"
            elif result.pdf_path:  # 备选pdf
                file_path = result.pdf_path
                file_ext = "pdf"
            else:
                # 如果没有生成文件，尝试从服务器下载原始文件
                file_path = f"outputs/{result.research_id}.md"
                file_ext = "md"
            
            if not file_path:
                raise ValueError("未找到可用的报告文件")
            
            # 创建临时文件（从服务器下载或使用本地路径）
            temp_file = None
            if file_path.startswith("outputs/"):
                # 需要从服务器下载
                async with GPTResearcherClient(base_url=self.gpt_researcher_url) as client:
                    temp_file = await client.download_file(file_path)
            else:
                # 已经是完整路径
                temp_file = file_path
            
            if not temp_file or not os.path.exists(temp_file):
                raise FileNotFoundError(f"报告文件不存在: {file_path}")
            
            # 构建文件名
            safe_query = re.sub(r'[^\w\-_\. ]', '_', task.query[:50])
            filename = f"研究报告_{safe_query}.{file_ext}"
            
            # 发送文件
            file_comp = File(name=filename, file=temp_file)
            chain = MessageChain([Plain("📄 研究完成！报告已生成文件："), file_comp])
            await task.event.send(chain)
            
            logger.info(f"研究任务 {task.task_id} 报告已通过文件发送: {filename}")
            
            # 清理临时文件（如果是下载的）
            if file_path.startswith("outputs/") and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"发送最终报告失败: {e}")
            # 回退到错误报告
            await self._send_error_report(task, f"发送报告文件失败: {e}")

    async def _send_error_report(self, task: ResearchTask, error_msg: str):
        """发送错误报告（仅文本）"""
        try:
            message = f"研究任务失败\n主题: {task.query}\n错误: {error_msg}"
            await task.event.reply(message)
            logger.error(f"研究任务 {task.task_id} 错误报告已发送: {error_msg}")
        except Exception as e:
            logger.error(f"发送错误报告失败: {e}")

    async def cancel_research_task(self, task_id: str):
        """取消研究任务"""
        if task_id in self.research_tasks:
            task = self.research_tasks[task_id]
            task.error = "任务取消。"
            self.active_tasks.discard(task_id)
            logger.info(f"研究任务 {task_id} 已取消")

    @filter.command("research")
    async def research_command(self, event: AstrMessageEvent, query: str):
        """启动研究任务
        用法: /research <研究主题>
        """
        # 权限检查：好友限制、白名单等
        permission_ok, reason = self._check_permission(event)
        if not permission_ok:
            logger.info(f"研究请求被拒绝: {reason}")
            yield event.plain_result(f"❌ 研究请求被拒绝: {reason}")
            return

        if not query or query.strip() == "":
            yield event.plain_result(f"请提供研究主题，例如：'/research 人工智能的最新发展'")
            return

        query = query.strip()
        # 发送确认消息
        yield event.plain_result(f"🔍 收到研究命令，主题: {query}\n开始研究...")

        # 启动研究任务
        await self.start_research_task(event, query)

    @filter.command("research_status")
    async def research_status(self, event: AstrMessageEvent):
        """查看研究任务状态"""
        if not self.research_tasks:
            yield event.plain_result("当前没有进行中的研究任务")
            return
        
        status_lines = ["研究任务状态:"]
        for task_id, task in self.research_tasks.items():
            status = "已完成" if task.completed else "进行中" if task.error is None else "失败"
            elapsed = int(time.time() - task.start_time)
            status_lines.append(f"- 任务 {task_id}: {status}")
            status_lines.append(f"  主题: {task.query[:30]}...")
            status_lines.append(f"  已运行: {elapsed}秒")
            if task.error:
                status_lines.append(f"  错误: {task.error}")
        
        yield event.plain_result("\n".join(status_lines))

    @filter.command("cancel_research")
    async def cancel_research(self, event: AstrMessageEvent):
        """取消所有研究任务"""
        if not self.active_tasks:
            yield event.plain_result("当前没有进行中的研究任务")
            return
        
        count = len(self.active_tasks)
        for task_id in list(self.active_tasks):
            await self.cancel_research_task(task_id)
        
        yield event.plain_result(f"已取消 {count} 个研究任务")