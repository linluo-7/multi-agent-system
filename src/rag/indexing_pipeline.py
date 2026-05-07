"""
Indexing Pipeline
增量索引管道 — 文件监听 / 定时扫描 / Webhook 触发
"""
import asyncio
import os
import hashlib
from pathlib import Path
from typing import Dict, Set, Optional, Callable
from datetime import datetime


class IncrementalIndexer:
    """增量索引器：监听目录变化，自动同步到知识库"""

    def __init__(self, watch_dir: str, rag_service, kb_name: str = 'default',
                 scan_interval: int = 60):
        self.watch_dir = Path(watch_dir)
        self.rag = rag_service
        self.kb_name = kb_name
        self.scan_interval = scan_interval
        self._file_hashes: Dict[str, str] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_change: Optional[Callable] = None

    @property
    def supported_extensions(self) -> Set[str]:
        return {'.pdf', '.docx', '.doc', '.txt', '.md', '.py', '.js',
                '.yaml', '.json', '.csv', '.html', '.xml'}

    def on_change(self, callback: Callable):
        """注册变更回调"""
        self._on_change = callback
        return self

    async def start(self):
        """启动定时扫描"""
        self._running = True
        self._task = asyncio.create_task(self._scan_loop())
        print(f"[Indexer] Started watching '{self.watch_dir}' "
              f"(interval={self.scan_interval}s, kb={self.kb_name})")

    async def stop(self):
        """停止扫描"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print(f"[Indexer] Stopped")

    async def scan_once(self) -> Dict[str, list]:
        """执行一次全量扫描，返回变更列表"""
        if not self.watch_dir.is_dir():
            return {'added': [], 'modified': [], 'deleted': []}

        current_files = set()
        added = []
        modified = []
        deleted = []

        for f in self.watch_dir.rglob('*'):
            if not f.is_file():
                continue
            if f.suffix.lower() not in self.supported_extensions:
                continue

            file_path = str(f)
            current_files.add(file_path)
            file_hash = self._compute_hash(str(f))

            if file_path not in self._file_hashes:
                added.append(file_path)
            elif self._file_hashes[file_path] != file_hash:
                modified.append(file_path)

            self._file_hashes[file_path] = file_hash

        # 检测删除
        for path in list(self._file_hashes.keys()):
            if path not in current_files:
                deleted.append(path)
                del self._file_hashes[path]

        # 处理变更
        for file_path in added:
            try:
                doc = await self.rag.import_document(file_path, kb_name=self.kb_name)
                print(f"[Indexer] Added: {Path(file_path).name}" +
                      (f" (id={doc.id})" if doc else " FAILED"))
            except Exception as e:
                print(f"[Indexer] Add error '{file_path}': {e}")

        for file_path in modified:
            try:
                doc_id = self._find_doc_id_by_path(file_path)
                if doc_id:
                    await self.rag.incremental_update_document(doc_id, file_path)
                    print(f"[Indexer] Updated: {Path(file_path).name}")
            except Exception as e:
                print(f"[Indexer] Update error '{file_path}': {e}")

        for file_path in deleted:
            print(f"[Indexer] Deleted: {Path(file_path).name} (manual cleanup needed)")

        if self._on_change and (added or modified or deleted):
            await self._on_change({
                'added': added, 'modified': modified, 'deleted': deleted,
                'timestamp': datetime.now().isoformat()
            })

        return {'added': added, 'modified': modified, 'deleted': deleted}

    async def _scan_loop(self):
        """后台扫描循环"""
        while self._running:
            try:
                await self.scan_once()
            except Exception as e:
                print(f"[Indexer] Scan error: {e}")
            await asyncio.sleep(self.scan_interval)

    def _compute_hash(self, file_path: str) -> str:
        """计算文件MD5"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ''

    def _find_doc_id_by_path(self, file_path: str) -> Optional[str]:
        """根据文件路径找到已索引的doc_id"""
        fname = Path(file_path).name
        for doc_id, doc in self.rag._docs.items():
            if doc.filename == fname:
                return doc_id
        return None

    def get_status(self) -> dict:
        return {
            'watch_dir': str(self.watch_dir),
            'kb_name': self.kb_name,
            'running': self._running,
            'scan_interval': self.scan_interval,
            'tracked_files': len(self._file_hashes)
        }
