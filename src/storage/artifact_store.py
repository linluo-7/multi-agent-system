"""
Artifact Store
产物版本管理 — 追踪任务产物，支持版本回溯和增量编辑
"""

import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class ArtifactStore:
    """产物版本管理与追溯"""

    def __init__(self, storage_dir: str = None):
        self.storage_dir = Path(storage_dir or '/tmp/artifacts')
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts: Dict[str, List[dict]] = {}
        self._metadata: Dict[str, dict] = {}

    def save_artifact(
        self,
        task_id: str,
        content: str,
        artifact_type: str = 'code',
        filename: str = None,
        metadata: dict = None
    ) -> str:
        """保存产物，自动版本管理"""
        if task_id not in self._artifacts:
            self._artifacts[task_id] = []

        version = len(self._artifacts[task_id]) + 1
        artifact_id = f"{task_id}_v{version}"

        filename = filename or f"{artifact_id}.{artifact_type}"
        file_path = self.storage_dir / task_id / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')

        entry = {
            'artifact_id': artifact_id,
            'task_id': task_id,
            'version': version,
            'filename': filename,
            'file_path': str(file_path),
            'artifact_type': artifact_type,
            'content_hash': self._hash_content(content),
            'content_preview': content[:200],
            'metadata': metadata or {},
            'created_at': datetime.now().isoformat()
        }

        self._artifacts[task_id].append(entry)

        print(f"[ArtifactStore] Saved artifact {artifact_id} ({len(content)} chars)")
        return artifact_id

    def get_artifact(self, task_id: str, version: int = None) -> Optional[dict]:
        """获取产物（默认最新版本）"""
        versions = self._artifacts.get(task_id, [])
        if not versions:
            return None

        if version is None:
            return versions[-1]
        return versions[version - 1] if 0 < version <= len(versions) else None

    def get_artifact_history(self, task_id: str) -> List[dict]:
        """获取产物版本历史"""
        return [
            {
                'version': v['version'],
                'created_at': v['created_at'],
                'artifact_type': v['artifact_type'],
                'preview': v['content_preview']
            }
            for v in self._artifacts.get(task_id, [])
        ]

    def get_artifact_content(self, task_id: str, version: int = None) -> Optional[str]:
        """获取产物内容"""
        artifact = self.get_artifact(task_id, version)
        if artifact is None:
            return None

        file_path = Path(artifact['file_path'])
        if file_path.exists():
            return file_path.read_text(encoding='utf-8')
        return None

    def diff_versions(self, task_id: str, v1: int, v2: int) -> dict:
        """比较两个版本的差异"""
        content1 = self.get_artifact_content(task_id, v1) or ''
        content2 = self.get_artifact_content(task_id, v2) or ''

        lines1 = content1.splitlines()
        lines2 = content2.splitlines()

        added = [l for l in lines2 if l not in lines1]
        removed = [l for l in lines1 if l not in lines2]

        return {
            'v1_lines': len(lines1),
            'v2_lines': len(lines2),
            'lines_added': len(added),
            'lines_removed': len(removed),
            'added_preview': added[:10],
            'removed_preview': removed[:10]
        }

    def rollback(self, task_id: str, target_version: int) -> Optional[str]:
        """回退到指定版本（创建新版本=目标版本内容）"""
        content = self.get_artifact_content(task_id, target_version)
        if content is None:
            print(f"[ArtifactStore] Rollback failed: version {target_version} not found")
            return None

        artifact = self.get_artifact(task_id, target_version)
        new_id = self.save_artifact(
            task_id=task_id,
            content=content,
            artifact_type=artifact['artifact_type'],
            filename=artifact['filename'],
            metadata={'rolled_back_from': target_version}
        )
        print(f"[ArtifactStore] Rollback: {task_id} -> v{target_version} content saved as {new_id}")
        return new_id

    def delete_artifacts(self, task_id: str):
        """删除所有产物"""
        if task_id in self._artifacts:
            del self._artifacts[task_id]
        import shutil
        task_dir = self.storage_dir / task_id
        if task_dir.exists():
            shutil.rmtree(task_dir)
        print(f"[ArtifactStore] Deleted all artifacts for task '{task_id}'")

    def get_stats(self) -> dict:
        """获取产物存储统计"""
        total_artifacts = sum(len(v) for v in self._artifacts.values())
        return {
            'total_tasks': len(self._artifacts),
            'total_artifacts': total_artifacts,
            'storage_dir': str(self.storage_dir)
        }

    def _hash_content(self, content: str) -> str:
        import hashlib
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:12]


_artifact_store: Optional[ArtifactStore] = None


def get_artifact_store(storage_dir: str = None) -> ArtifactStore:
    global _artifact_store
    if _artifact_store is None:
        _artifact_store = ArtifactStore(storage_dir)
    return _artifact_store
