"""
Document Loader
多格式文档解析器 — 支持 PDF、Word、TXT 批量导入与自动解析清洗
"""

import re
import asyncio
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Document:
    """文档数据结构"""
    id: str
    filename: str
    file_type: str  # pdf / word / txt
    content: str
    chunks: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'filename': self.filename,
            'file_type': self.file_type,
            'content_preview': self.content[:200],
            'chunk_count': len(self.chunks),
            'metadata': self.metadata,
            'created_at': self.created_at
        }


class DocumentLoader:
    """多格式文档加载与解析器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.chunk_size = self.config.get('chunk_size', 500)
        self.chunk_overlap = self.config.get('chunk_overlap', 50)

    async def load_file(self, file_path: str) -> Optional[Document]:
        """加载单个文件并自动识别格式"""
        path = Path(file_path)
        if not path.exists():
            print(f"[DocLoader] File not found: {file_path}")
            return None

        suffix = path.suffix.lower()
        if suffix == '.pdf':
            return await self._load_pdf(path)
        elif suffix in ('.docx', '.doc'):
            return await self._load_word(path)
        elif suffix in ('.txt', '.md', '.py', '.js', '.yaml', '.json', '.csv'):
            return await self._load_text(path)
        else:
            print(f"[DocLoader] Unsupported format: {suffix}")
            return None

    async def load_directory(self, dir_path: str) -> List[Document]:
        """批量加载目录下所有支持的文档"""
        path = Path(dir_path)
        if not path.is_dir():
            return []

        tasks = []
        for f in path.rglob('*'):
            if f.suffix.lower() in ('.pdf', '.docx', '.doc', '.txt', '.md'):
                tasks.append(self.load_file(str(f)))

        results = await asyncio.gather(*tasks)
        return [doc for doc in results if doc is not None]

    async def _load_pdf(self, path: Path) -> Document:
        """解析PDF文档"""
        content = ""
        try:
            import fitz  # pymupdf
            loop = asyncio.get_event_loop()

            def extract():
                text_parts = []
                doc = fitz.open(str(path))
                for page in doc:
                    text_parts.append(page.get_text())
                doc.close()
                return '\n'.join(text_parts)

            content = await loop.run_in_executor(None, extract)
        except ImportError:
            content = f"[PDF content placeholder: {path.name}]"
        except Exception as e:
            print(f"[DocLoader] PDF parse error: {e}")
            content = f"[PDF parse error for {path.name}]"

        return self._build_document(path, content, 'pdf')

    async def _load_word(self, path: Path) -> Document:
        """解析Word文档"""
        content = ""
        try:
            from docx import Document as DocxDocument
            loop = asyncio.get_event_loop()

            def extract():
                doc = DocxDocument(str(path))
                return '\n'.join(p.text for p in doc.paragraphs)

            content = await loop.run_in_executor(None, extract)
        except ImportError:
            content = f"[Word content placeholder: {path.name}]"
        except Exception as e:
            print(f"[DocLoader] Word parse error: {e}")
            content = f"[Word parse error for {path.name}]"

        return self._build_document(path, content, 'word')

    async def _load_text(self, path: Path) -> Document:
        """解析纯文本/TXT/Markdown等"""
        content = ""
        try:
            loop = asyncio.get_event_loop()

            def read_file():
                return path.read_text(encoding='utf-8', errors='replace')

            content = await loop.run_in_executor(None, read_file)
        except Exception as e:
            print(f"[DocLoader] Text read error: {e}")
            content = f"[Read error for {path.name}]"

        return self._build_document(path, content, path.suffix.lstrip('.'))

    def _build_document(self, path: Path, raw_content: str, file_type: str) -> Document:
        """构建Document对象并进行清洗分块"""
        cleaned = self._clean_text(raw_content)
        chunks = self._chunk_text(cleaned)

        import uuid
        return Document(
            id=str(uuid.uuid4()),
            filename=path.name,
            file_type=file_type,
            content=cleaned,
            chunks=chunks,
            metadata={
                'source_path': str(path),
                'file_size': path.stat().st_size if path.exists() else 0,
                'char_count': len(cleaned),
                'chunk_count': len(chunks)
            }
        )

    def _clean_text(self, text: str) -> str:
        """文本清洗"""
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        text = re.sub(r'\t+', ' ', text)
        # 移除控制字符（保留常见换行制表符）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        return text.strip()

    def _chunk_text(self, text: str) -> List[str]:
        """文本分块，支持滑动窗口重叠"""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            if end < len(text):
                # 优先在句末断句
                for sep in ['。\n', '。', '.\n', '.', '\n\n', '\n']:
                    last = chunk.rfind(sep)
                    if last > self.chunk_size // 2:
                        end = start + last + len(sep)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - self.chunk_overlap

        return chunks

    def get_chunk_statistics(self, document: Document) -> dict:
        """获取文档分块统计"""
        return {
            'filename': document.filename,
            'total_chars': len(document.content),
            'chunk_count': len(document.chunks),
            'avg_chunk_size': sum(len(c) for c in document.chunks) / len(document.chunks) if document.chunks else 0,
            'file_type': document.file_type
        }
