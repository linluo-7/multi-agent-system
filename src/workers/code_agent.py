"""
Code Agent
代码Agent - 负责代码编写、修改和执行
"""

import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from .base import BaseWorker


class CodeAgent(BaseWorker):
    """代码编写Agent"""
    
    name = "code"
    description = "代码编写Agent，负责编写、修改和执行代码"
    
    def __init__(self, config: dict, redis_manager, postgres_storage):
        super().__init__(config, redis_manager, postgres_storage)
        self.workspace = Path(config.get('workspace', '/tmp/code_agent_workspace'))
        self.workspace.mkdir(parents=True, exist_ok=True)
    
    async def execute(self, task: dict, context: dict) -> dict:
        """
        执行代码任务
        
        Expected task format:
        {
            "type": "code",
            "input": {
                "action": "write" | "read" | "execute" | "modify",
                "language": "python" | "javascript" | "bash" | ...",
                "filename": "main.py",  # optional
                "code": "...",         # for write/modify
                "command": "...",      # for execute
                "path": "..."          # for read
            }
        }
        """
        task_input = task.get('input', {})
        action = task_input.get('action', 'execute')
        language = task_input.get('language', 'python')
        
        # 根据上下文补充信息
        blackboard = context.get('blackboard', {})
        search_results = self._extract_from_blackboard(blackboard, 'search')
        
        result = {'action': action, 'language': language}
        
        if action == 'write':
            filename = task_input.get('filename', f'temp.{language}')
            code = task_input.get('code', '')
            file_path = self.workspace / filename
            
            # 写入文件
            file_path.write_text(code)
            result.update({
                'status': 'success',
                'path': str(file_path),
                'bytes_written': len(code)
            })
            
        elif action == 'read':
            path = task_input.get('path', '')
            file_path = Path(path) if Path(path).is_absolute() else self.workspace / path
            
            if file_path.exists():
                content = file_path.read_text()
                result.update({
                    'status': 'success',
                    'path': str(file_path),
                    'content': content,
                    'lines': len(content.splitlines())
                })
            else:
                result.update({
                    'status': 'error',
                    'error': f'File not found: {file_path}'
                })
                
        elif action == 'execute':
            command = task_input.get('command', '')
            timeout = task_input.get('timeout', 30)
            
            # 如果有搜索结果，将其注入为环境变量或文件
            if search_results:
                context_file = self.workspace / '.context.json'
                context_file.write_text(str(search_results))
            
            # 执行命令
            exec_result = await self._execute_command(command, timeout)
            result.update(exec_result)
            
        elif action == 'modify':
            # 从黑板读取其他Agent提供的信息，辅助代码修改
            code = task_input.get('code', '')
            modifications = task_input.get('modifications', [])
            
            modified_code = code
            for mod in modifications:
                # 简单应用修改指令
                mod_type = mod.get('type')
                if mod_type == 'replace':
                    modified_code = modified_code.replace(mod['old'], mod['new'])
            
            result.update({
                'status': 'success',
                'original_lines': len(code.splitlines()),
                'modified_lines': len(modified_code.splitlines()),
                'modified_code': modified_code
            })
        
        return result
    
    async def _execute_command(self, command: str, timeout: int) -> dict:
        """执行系统命令"""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                return {
                    'status': 'completed',
                    'returncode': process.returncode,
                    'stdout': stdout.decode('utf-8', errors='replace'),
                    'stderr': stderr.decode('utf-8', errors='replace'),
                    'execution_time': f'{timeout}s'
                }
            except asyncio.TimeoutError:
                process.kill()
                return {
                    'status': 'timeout',
                    'timeout_seconds': timeout,
                    'error': f'Command timed out after {timeout} seconds'
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _extract_from_blackboard(self, blackboard: dict, agent_prefix: str) -> Optional[dict]:
        """从黑板提取特定Agent的数据"""
        for key, value in blackboard.items():
            if key.startswith(agent_prefix):
                return value.get('data')
        return None
    
    def get_workspace_path(self) -> Path:
        """获取工作区路径"""
        return self.workspace
