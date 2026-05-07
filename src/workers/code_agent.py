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
            
            # 执行命令（优先沙箱）
            use_sandbox = task_input.get('sandbox', self.config.get('sandbox', {}).get('enabled', False))
            if use_sandbox:
                exec_result = await self._execute_sandboxed(command, timeout, language)
            else:
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

    async def _execute_sandboxed(self, command: str, timeout: int = 30, language: str = 'python') -> dict:
        """
        沙箱化执行命令

        安全措施：
        1. Docker容器隔离执行
        2. 资源限制（CPU/内存/网络）
        3. 超时控制
        4. 白名单命令检查
        5. 无网络模式（默认）
        """
        # 1. 命令白名单检查
        if not self._is_safe_command(command):
            return {
                'status': 'blocked',
                'error': 'Command blocked by security policy: dangerous operation detected',
                'sandboxed': True
            }

        # 2. 尝试Docker沙箱执行
        sandbox_config = self.config.get('sandbox', {})
        use_docker = sandbox_config.get('use_docker', False)
        sandbox_image = sandbox_config.get('image', 'python:3.12-slim')

        if use_docker:
            return await self._docker_sandbox_exec(
                command, timeout, language, sandbox_image,
                sandbox_config.get('memory_limit', '256m'),
                sandbox_config.get('cpu_limit', '0.5'),
                sandbox_config.get('network_disabled', True),
                sandbox_config.get('read_only', True)
            )

        # 3. 回退到本地受限执行
        return await self._local_sandbox_exec(command, timeout)

    def _is_safe_command(self, command: str) -> bool:
        """安全检查：命令白名单"""
        blocked_patterns = [
            'rm -rf /', 'mkfs.', 'dd if=', ':(){ :|:& };:',  # fork bomb
            '> /dev/sda', 'chmod 777 /', 'wget', 'curl',
            'nc ', 'ncat ', 'telnet',  # 网络工具
            'sudo ', 'su ', 'passwd',
            'shutdown', 'reboot', 'halt',
            'export ', 'unset ',  # 环境变量操作
        ]
        cmd_lower = command.lower()
        for pattern in blocked_patterns:
            if pattern in cmd_lower:
                return False
        return True

    async def _docker_sandbox_exec(
        self, command: str, timeout: int, language: str,
        image: str, memory_limit: str, cpu_limit: str,
        network_disabled: bool, read_only: bool
    ) -> dict:
        """Docker容器沙箱执行"""
        docker_cmd = [
            'docker', 'run', '--rm',
            f'--memory={memory_limit}',
            f'--cpus={cpu_limit}',
            '--tmpfs', '/tmp:exec',
        ]

        if network_disabled:
            docker_cmd.append('--network=none')

        if read_only:
            docker_cmd.extend(['--read-only', '--tmpfs', '/home:rw,exec'])

        docker_cmd.extend([
            '-v', f'{self.workspace}:/workspace:rw',
            '-w', '/workspace',
            image,
            'sh', '-c', command
        ])

        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                return {
                    'status': 'completed',
                    'returncode': process.returncode,
                    'stdout': stdout.decode('utf-8', errors='replace'),
                    'stderr': stderr.decode('utf-8', errors='replace'),
                    'sandboxed': True,
                    'sandbox_type': 'docker'
                }
            except asyncio.TimeoutError:
                process.kill()
                return {
                    'status': 'timeout',
                    'timeout_seconds': timeout,
                    'error': f'Sandbox execution timed out after {timeout}s',
                    'sandboxed': True,
                    'sandbox_type': 'docker'
                }
        except FileNotFoundError:
            print("[CodeAgent] Docker not available, falling back to local sandbox")
            return await self._local_sandbox_exec(command, timeout)
        except Exception as e:
            return {
                'status': 'sandbox_error',
                'error': str(e),
                'sandboxed': False
            }

    async def _local_sandbox_exec(self, command: str, timeout: int) -> dict:
        """本地受限执行（非沙箱回退方案）"""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                # 安全限制
                preexec_fn=None  # Windows兼容
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                return {
                    'status': 'completed',
                    'returncode': process.returncode,
                    'stdout': stdout.decode('utf-8', errors='replace')[:10000],
                    'stderr': stderr.decode('utf-8', errors='replace')[:5000],
                    'sandboxed': False,
                    'sandbox_type': 'local'
                }
            except asyncio.TimeoutError:
                process.kill()
                return {
                    'status': 'timeout',
                    'timeout_seconds': timeout,
                    'error': f'Execution timed out after {timeout}s',
                    'sandboxed': False
                }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'sandboxed': False
            }
