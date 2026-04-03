"""
Doc Agent
文档Agent - 负责生成和处理各类文档
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from .base import BaseWorker


class DocAgent(BaseWorker):
    """文档生成Agent"""
    
    name = "doc"
    description = "文档生成Agent，负责生成和处理各类文档"
    
    def __init__(self, config: dict, redis_manager, postgres_storage):
        super().__init__(config, redis_manager, postgres_storage)
        self.output_dir = Path(config.get('output_dir', '/tmp/doc_agent_output'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def execute(self, task: dict, context: dict) -> dict:
        """
        执行文档任务
        
        Expected task format:
        {
            "type": "doc",
            "input": {
                "action": "generate" | "summarize" | "format" | "export",
                "format": "markdown" | "word" | "json" | "html",
                "content": "...",        # for generate
                "source": "...",         # for summarize (file path or text)
                "template": "...",       # for generate (optional)
                "data": {...}            # for generate with template
            }
        }
        """
        task_input = task.get('input', {})
        action = task_input.get('action', 'generate')
        doc_format = task_input.get('format', 'markdown')
        
        # 从上下文获取素材
        blackboard = context.get('blackboard', {})
        search_data = self._extract_agent_data(blackboard, 'search')
        code_data = self._extract_agent_data(blackboard, 'code')
        
        result = {'action': action, 'format': doc_format}
        
        if action == 'generate':
            content = task_input.get('content', '')
            template = task_input.get('template')
            data = task_input.get('data', {})
            
            # 如果有搜索或代码结果，合并到内容中
            if search_data and not content:
                content = self._generate_from_search(content, search_data)
            
            if template and data:
                final_content = self._apply_template(template, data)
            else:
                final_content = content or self._generate_default(content, doc_format, search_data, code_data)
            
            # 保存文档
            filename = task_input.get('filename', f'document_{datetime.now().strftime("%Y%m%d_%H%M%S")}.{doc_format}')
            file_path = self.output_dir / filename
            file_path.write_text(final_content, encoding='utf-8')
            
            result.update({
                'status': 'success',
                'path': str(file_path),
                'filename': filename,
                'size_bytes': len(final_content.encode('utf-8')),
                'preview': final_content[:500] + '...' if len(final_content) > 500 else final_content
            })
            
        elif action == 'summarize':
            source = task_input.get('source', '')
            
            # 判断source是文件还是文本
            if Path(source).exists():
                content = Path(source).read_text(encoding='utf-8')
            else:
                content = source
            
            summary = self._summarize_text(content)
            result.update({
                'status': 'success',
                'original_length': len(content),
                'summary_length': len(summary),
                'summary': summary
            })
            
        elif action == 'format':
            content = task_input.get('content', '')
            style = task_input.get('style', 'default')
            
            formatted = self._format_content(content, doc_format, style)
            result.update({
                'status': 'success',
                'formatted_content': formatted
            })
            
        elif action == 'export':
            # 导出为指定格式
            data = task_input.get('data', {})
            filename = task_input.get('filename', f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            
            if doc_format == 'json':
                content = json.dumps(data, ensure_ascii=False, indent=2)
                filename += '.json'
            elif doc_format == 'html':
                content = self._generate_html(data)
                filename += '.html'
            else:
                content = str(data)
                filename += f'.{doc_format}'
            
            file_path = self.output_dir / filename
            file_path.write_text(content, encoding='utf-8')
            
            result.update({
                'status': 'success',
                'path': str(file_path),
                'filename': filename
            })
        
        return result
    
    def _extract_agent_data(self, blackboard: dict, agent_name: str) -> Optional[dict]:
        """从黑板提取特定Agent的数据"""
        for key, value in blackboard.items():
            if key == agent_name or key.startswith(f'{agent_name}_'):
                return value.get('data')
        return None
    
    def _generate_from_search(self, content: str, search_data: dict) -> str:
        """基于搜索结果生成内容"""
        if not content:
            content = "# 搜索报告\n\n"
        
        results = search_data.get('results', [])
        if results:
            content += "\n## 参考资料\n\n"
            for i, r in enumerate(results[:5], 1):
                title = r.get('title', '无标题')
                url = r.get('url', '')
                snippet = r.get('snippet', '')
                content += f"{i}. **{title}**\n   - 来源: {url}\n   - 摘要: {snippet}\n\n"
        
        return content
    
    def _generate_default(self, content: str, doc_format: str, search_data: dict, code_data: dict) -> str:
        """生成默认文档"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if doc_format == 'markdown':
            doc = f"""# 文档

> 生成时间: {timestamp}

## 内容

{content or '（无内容）'}

## 补充信息

"""
            if search_data:
                doc += f"- 搜索结果数: {search_data.get('count', 0)}\n"
            if code_data:
                doc += f"- 代码状态: {code_data.get('status', 'unknown')}\n"
            
            return doc
        else:
            return content or f"Document generated at {timestamp}"
    
    def _apply_template(self, template: str, data: dict) -> str:
        """应用模板生成内容"""
        # 简单的模板替换
        result = template
        for key, value in data.items():
            placeholder = f'{{{{{key}}}}}'
            result = result.replace(placeholder, str(value))
        return result
    
    def _summarize_text(self, content: str, max_length: int = 500) -> str:
        """总结文本"""
        if len(content) <= max_length:
            return content
        
        # 简单截取前max_length个字符
        summary = content[:max_length]
        
        # 尝试在句号或逗号处截断
        last_period = max(summary.rfind('。'), summary.rfind('.'))
        if last_period > max_length * 0.5:
            summary = summary[:last_period + 1]
        
        return summary + '...'
    
    def _format_content(self, content: str, doc_format: str, style: str) -> str:
        """格式化内容"""
        if doc_format == 'markdown':
            # 确保有适当的标题层级
            lines = content.splitlines()
            formatted_lines = []
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    line = '## ' + line
                formatted_lines.append(line)
            return '\n'.join(formatted_lines)
        else:
            return content
    
    def _generate_html(self, data: dict) -> str:
        """生成HTML"""
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{data.get('title', 'Document')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        pre {{ background: #f5f5f5; padding: 20px; }}
    </style>
</head>
<body>
    <h1>{data.get('title', 'Document')}</h1>
    <pre>{json.dumps(data, ensure_ascii=False, indent=2)}</pre>
</body>
</html>"""
    
    def get_output_dir(self) -> Path:
        """获取输出目录"""
        return self.output_dir
