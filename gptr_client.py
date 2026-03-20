"""
GPT-Researcher HTTP 客户端
用于与 gpt-researcher 后端服务通信的独立客户端
"""
import aiohttp
import asyncio
import json
import time
import logging
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ReportType(Enum):
    """报告类型枚举"""
    RESEARCH_REPORT = "research_report"
    DEEP = "deep"
    MULTI_AGENTS = "multi_agents"


class ReportSource(Enum):
    """报告来源枚举"""
    WEB = "web"
    DOCUMENTS = "documents"
    HYBRID = "hybrid"


class Tone(Enum):
    """报告语气枚举"""
    OBJECTIVE = "Objective"
    ACADEMIC = "Academic"
    ANALYTICAL = "Analytical"
    CONVERSATIONAL = "Conversational"
    PERSUASIVE = "Persuasive"


@dataclass
class ResearchRequest:
    """研究请求参数"""
    task: str
    report_type: Union[str, ReportType] = ReportType.RESEARCH_REPORT.value
    report_source: Union[str, ReportSource] = ReportSource.WEB.value
    tone: Union[str, Tone] = Tone.OBJECTIVE.value
    source_urls: List[str] = None
    document_urls: List[str] = None
    query_domains: List[str] = None
    generate_in_background: bool = False
    headers: Optional[Dict] = None
    repo_name: str = ""
    branch_name: str = ""

    def __post_init__(self):
        if self.source_urls is None:
            self.source_urls = []
        if self.document_urls is None:
            self.document_urls = []
        if self.query_domains is None:
            self.query_domains = []
        
        # 确保枚举值转换为字符串
        if isinstance(self.report_type, ReportType):
            self.report_type = self.report_type.value
        if isinstance(self.report_source, ReportSource):
            self.report_source = self.report_source.value
        if isinstance(self.tone, Tone):
            self.tone = self.tone.value


@dataclass
class ResearchResult:
    """研究结果"""
    research_id: str
    report: str
    docx_path: Optional[str] = None
    pdf_path: Optional[str] = None
    research_information: Optional[Dict] = None
    error: Optional[str] = None


class GPTResearcherClient:
    """GPT-Researcher HTTP 客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 300):
        """
        初始化客户端
        
        Args:
            base_url: gpt-researcher 后端服务地址
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def connect(self):
        """创建 HTTP 会话"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
    async def close(self):
        """关闭 HTTP 会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            
    async def health_check(self) -> bool:
        """健康检查，确认服务是否可用"""
        try:
            async with self.session.get(f"{self.base_url}/") as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    async def generate_report(self, request: ResearchRequest) -> ResearchResult:
        """
        生成研究报告
        
        Args:
            request: 研究请求参数
            
        Returns:
            ResearchResult: 研究结果
        """
        await self.connect()
        
        # 准备请求数据
        payload = {
            "task": request.task,
            "report_type": request.report_type,
            "report_source": request.report_source,
            "tone": request.tone,
            "headers": request.headers or {},
            "repo_name": request.repo_name,
            "branch_name": request.branch_name,
            "generate_in_background": request.generate_in_background
        }
        
        try:
            logger.info(f"Generating report for task: {request.task[:50]}...")
            start_time = time.time()
            
            async with self.session.post(
                f"{self.base_url}/report/",
                json=payload,
                timeout=self.timeout
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Report generation failed: {response.status} - {error_text}")
                    return ResearchResult(
                        research_id="",
                        report="",
                        error=f"HTTP {response.status}: {error_text[:200]}"
                    )
                
                result_data = await response.json()
                
                # 如果后台生成，只返回 research_id
                if request.generate_in_background:
                    research_id = result_data.get("research_id", "")
                    message = result_data.get("message", "")
                    logger.info(f"Report generation started in background: {research_id}")
                    return ResearchResult(
                        research_id=research_id,
                        report=message,
                        error=None
                    )
                
                # 同步生成，返回完整结果
                research_id = result_data.get("research_id", "")
                report = result_data.get("report", "")
                docx_path = result_data.get("docx_path")
                pdf_path = result_data.get("pdf_path")
                research_info = result_data.get("research_information")
                
                elapsed = time.time() - start_time
                logger.info(f"Report generated in {elapsed:.1f}s, length: {len(report)} chars")
                
                return ResearchResult(
                    research_id=research_id,
                    report=report,
                    docx_path=docx_path,
                    pdf_path=pdf_path,
                    research_information=research_info,
                    error=None
                )
                
        except asyncio.TimeoutError:
            error_msg = f"Report generation timeout after {self.timeout}s"
            logger.error(error_msg)
            return ResearchResult(
                research_id="",
                report="",
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Report generation failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return ResearchResult(
                research_id="",
                report="",
                error=error_msg
            )
    
    async def get_report_by_id(self, research_id: str) -> Optional[Dict]:
        """
        根据 ID 获取报告
        
        Args:
            research_id: 研究任务 ID
            
        Returns:
            Optional[Dict]: 报告数据，如果不存在则返回 None
        """
        await self.connect()
        
        try:
            async with self.session.get(
                f"{self.base_url}/api/reports/{research_id}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("report")
                elif response.status == 404:
                    logger.warning(f"Report not found: {research_id}")
                    return None
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to get report: {response.status} - {error_text}")
                    return None
        except Exception as e:
            logger.error(f"Failed to get report: {e}")
            return None
    
    async def download_file(self, file_path: str, save_to: Optional[Path] = None) -> Optional[Path]:
        """
        下载输出文件（PDF/DOCX）
        
        Args:
            file_path: 文件在服务器上的路径（相对路径）
            save_to: 本地保存路径，如果为 None 则使用文件名
            
        Returns:
            Optional[Path]: 保存的文件路径，如果失败则返回 None
        """
        await self.connect()
        
        # 从 file_path 中提取文件名
        if file_path.startswith("outputs/"):
            filename = Path(file_path).name
        else:
            filename = Path(file_path).name
            
        if save_to is None:
            save_to = Path.cwd() / filename
        elif save_to.is_dir():
            save_to = save_to / filename
            
        try:
            async with self.session.get(
                f"{self.base_url}/{file_path.lstrip('/')}"
            ) as response:
                if response.status == 200:
                    content = await response.read()
                    save_to.write_bytes(content)
                    logger.info(f"File downloaded: {save_to}")
                    return save_to
                else:
                    logger.error(f"Failed to download file: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"File download failed: {e}")
            return None
    
    async def chat_with_report(self, report: str, messages: List[Dict]) -> Optional[Dict]:
        """
        与报告进行对话
        
        Args:
            report: 报告内容
            messages: 消息历史
            
        Returns:
            Optional[Dict]: 助手回复
        """
        await self.connect()
        
        payload = {
            "report": report,
            "messages": messages
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response")
                else:
                    error_text = await response.text()
                    logger.error(f"Chat failed: {response.status} - {error_text}")
                    return None
        except Exception as e:
            logger.error(f"Chat request failed: {e}")
            return None
    
    async def list_output_files(self) -> List[str]:
        """
        列出输出目录中的文件
        
        Returns:
            List[str]: 文件列表
        """
        await self.connect()
        
        try:
            async with self.session.get(f"{self.base_url}/files/") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("files", [])
                else:
                    return []
        except Exception:
            return []


# 简化的同步包装器（用于非异步环境）
class SyncGPTResearcherClient:
    """同步包装的 GPT-Researcher 客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 300):
        self.base_url = base_url
        self.timeout = timeout
        self._client = GPTResearcherClient(base_url, timeout)
        self._loop = None
        
    def _ensure_loop(self):
        """确保事件循环存在"""
        try:
            import asyncio
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
    
    def generate_report(self, request: ResearchRequest) -> ResearchResult:
        """同步生成报告"""
        self._ensure_loop()
        return self._loop.run_until_complete(
            self._client.generate_report(request)
        )
    
    def get_report_by_id(self, research_id: str) -> Optional[Dict]:
        """同步获取报告"""
        self._ensure_loop()
        return self._loop.run_until_complete(
            self._client.get_report_by_id(research_id)
        )
    
    def health_check(self) -> bool:
        """同步健康检查"""
        self._ensure_loop()
        return self._loop.run_until_complete(
            self._client.health_check()
        )
    
    def close(self):
        """同步关闭"""
        if self._loop:
            self._loop.run_until_complete(self._client.close())


# 使用示例
async def example_usage():
    """使用示例"""
    client = GPTResearcherClient()
    
    # 健康检查
    if not await client.health_check():
        print("服务不可用，请确保 gpt-researcher 后端正在运行")
        return
    
    # 创建研究请求
    request = ResearchRequest(
        task="人工智能的最新发展",
        report_type=ReportType.DEEP.value,
        report_source=ReportSource.WEB.value,
        tone=Tone.OBJECTIVE.value,
        generate_in_background=False
    )
    
    # 生成报告
    result = await client.generate_report(request)
    
    if result.error:
        print(f"错误: {result.error}")
    else:
        print(f"研究 ID: {result.research_id}")
        print(f"报告长度: {len(result.report)} 字符")
        print(f"DOCX 路径: {result.docx_path}")
        print(f"PDF 路径: {result.pdf_path}")
        
        # 如果需要，下载文件
        if result.docx_path:
            await client.download_file(result.docx_path, Path("./reports"))
    
    await client.close()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())