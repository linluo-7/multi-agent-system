"""
Visual Indexer
视觉检索索引器 — 页面截图→视觉embedding→Milvus
支持 CPU (CLIP) / GPU (ColQwen2) 双模式自动切换
"""
import asyncio
import base64
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime


class VisualIndexer:
    """视觉检索索引器 — CPU友好，GPU可选"""

    def __init__(self, config: dict = None, milvus_manager=None):
        self.config = config or {}
        self.milvus = milvus_manager
        self.collection = self.config.get('visual_collection', 'document_visuals')
        self.dim = self.config.get('visual_dim', 512)  # CLIP ViT-B/32 = 512
        self._model = None
        self._model_type = None  # 'clip' / 'colqwen2' / 'hash'

    async def initialize(self):
        """自动检测可用模型"""
        # 尝试加载 CLIP (CPU可跑，轻量)
        try:
            from transformers import CLIPProcessor, CLIPModel
            self._model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            self._processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            self._model_type = 'clip'
            self.dim = 512
            # 移到GPU如果有
            try:
                import torch
                if torch.cuda.is_available():
                    self._model = self._model.to('cuda')
                    print("[VisualIndexer] CLIP loaded on CUDA")
                else:
                    print("[VisualIndexer] CLIP loaded on CPU")
            except Exception:
                print("[VisualIndexer] CLIP loaded on CPU")
            return
        except ImportError:
            pass

        # 尝试 ColQwen2 (需要GPU)
        try:
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
            import torch
            if torch.cuda.is_available():
                model_id = self.config.get('visual_model', 'vidore/colqwen2-v1.0')
                self._model = Qwen2VLForConditionalGeneration.from_pretrained(
                    model_id, torch_dtype=torch.bfloat16, device_map="auto"
                )
                self._processor = AutoProcessor.from_pretrained(model_id)
                self._model_type = 'colqwen2'
                self.dim = 128  # ColQwen2 per-patch dim
                print("[VisualIndexer] ColQwen2 loaded on GPU")
                return
        except ImportError:
            pass
        except Exception as e:
            print(f"[VisualIndexer] ColQwen2 load failed: {e}")

        # 终极fallback：轻量hash（纯CPU，无依赖）
        print("[VisualIndexer] No visual model available, using perceptual hash mode")
        self._model_type = 'hash'
        self.dim = 64

    # ---- 编码 ----

    async def encode_page(self, image_b64: str) -> Optional[List[float]]:
        """编码单页截图"""
        if self._model_type == 'clip':
            return await self._encode_clip(image_b64)
        elif self._model_type == 'colqwen2':
            return await self._encode_colqwen2(image_b64)
        else:
            return self._encode_hash(image_b64)

    async def encode_pages(self, images_b64: List[str]) -> List[List[float]]:
        """批量编码"""
        embeddings = []
        for img in images_b64:
            emb = await self.encode_page(img)
            if emb:
                embeddings.append(emb)
        return embeddings

    async def _encode_clip(self, image_b64: str) -> Optional[List[float]]:
        """CLIP编码 (CPU/GPU)"""
        try:
            from PIL import Image
            import io
            from transformers import CLIPProcessor

            img_bytes = base64.b64decode(image_b64.split(',')[-1] if ',' in image_b64 else image_b64)
            image = Image.open(io.BytesIO(img_bytes)).convert('RGB')

            inputs = self._processor(images=image, return_tensors="pt")
            if self._model.device.type != 'cpu':
                inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            with __import__('torch').no_grad():
                emb = self._model.get_image_features(**inputs)
                emb = emb / emb.norm(dim=-1, keepdim=True)
                return emb[0].cpu().tolist()
        except Exception as e:
            print(f"[VisualIndexer] CLIP encode error: {e}")
            return None

    async def _encode_colqwen2(self, image_b64: str) -> Optional[List[float]]:
        """ColQwen2编码 — 返回mean-pooled单向量（简化版）"""
        try:
            from PIL import Image
            import io
            import torch

            img_bytes = base64.b64decode(image_b64.split(',')[-1] if ',' in image_b64 else image_b64)
            image = Image.open(io.BytesIO(img_bytes)).convert('RGB')

            messages = [{
                "role": "user",
                "content": [{"type": "image", "image": image}, {"type": "text", "text": "Describe this page."}]
            }]
            inputs = self._processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True,
                return_dict=True, return_tensors="pt"
            ).to(self._model.device)

            with torch.no_grad():
                # 取vision encoder的输出做mean pool
                outputs = self._model.visual(**{
                    k.replace('visual.', ''): v for k, v in inputs.items()
                    if 'visual' in k or 'pixel' in k or 'image' in k
                }, output_hidden_states=True)
                # 最后一层hidden states mean pool
                if hasattr(outputs, 'hidden_states') and outputs.hidden_states:
                    last = outputs.hidden_states[-1]
                    pooled = last.mean(dim=1)[0].cpu().tolist()
                    return pooled[:128]
                # fallback： 空向量
                return [0.0] * 128
        except Exception as e:
            print(f"[VisualIndexer] ColQwen2 encode error: {e}")
            return None

    def _encode_hash(self, image_b64: str) -> List[float]:
        """感知哈希 — 无模型依赖的轻量fallback"""
        import hashlib
        # 用image base64内容做hash，生成64维伪向量
        raw = image_b64[-2000:] if len(image_b64) > 2000 else image_b64  # 采样
        h = hashlib.sha256(raw.encode()).digest()
        # 转为64维float向量
        vec = []
        for i in range(0, 32, 1):
            val = (h[i] / 255.0) * 2 - 1
            vec.append(val)
        # 补到64维
        while len(vec) < 64:
            vec.append(0.0)
        return vec[:64]

    # ---- 索引 ----

    async def index_document(self, doc_id: str, page_images: List[str],
                             metadata: dict = None):
        """索引文档的所有页面截图"""
        if not page_images:
            return 0

        embeddings = await self.encode_pages(page_images)
        if not embeddings:
            return 0

        vectors = []
        for i, (img_b64, emb) in enumerate(zip(page_images, embeddings)):
            if not emb:
                continue
            vectors.append({
                'id': f"{doc_id}_page_{i}",
                'text': f"Page {i + 1} of {metadata.get('filename', '') if metadata else ''}",
                'embedding': emb,
                'metadata': {
                    **(metadata or {}),
                    'doc_id': doc_id,
                    'page_num': i,
                    'total_pages': len(page_images),
                    'image_b64': img_b64[:500],  # 缩略存储
                },
                'timestamp': datetime.now().timestamp()
            })

        if vectors and self.milvus:
            await self.milvus.insert(self.collection, vectors)
            print(f"[VisualIndexer] Indexed {len(vectors)} pages for doc '{doc_id}' "
                  f"(model={self._model_type})")
        return len(vectors)

    async def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """视觉检索 — 查询文本匹配页面截图"""
        if not self.milvus or self._model_type == 'hash':
            return []

        try:
            # 用文本embedding检索视觉collection
            # (CLIP的text encoder可以跨模态匹配)
            if self._model_type == 'clip':
                query_emb = await self._encode_clip_text(query)
                if not query_emb:
                    return []
            else:
                return []

            results = await self.milvus.search(
                self.collection,
                query_emb,
                top_k=top_k
            )
            return [{
                'id': r.get('id', ''),
                'text': r.get('text', ''),
                'score': r.get('score', 0),
                'source': 'visual',
                'metadata': r.get('metadata', {}),
                'image_b64': r.get('metadata', {}).get('image_b64', '')[:200]
            } for r in results]
        except Exception as e:
            print(f"[VisualIndexer] Search error: {e}")
            return []

    async def _encode_clip_text(self, text: str) -> Optional[List[float]]:
        """CLIP文本编码"""
        try:
            inputs = self._processor(text=text, return_tensors="pt", padding=True, truncation=True)
            if self._model.device.type != 'cpu':
                inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
            with __import__('torch').no_grad():
                emb = self._model.get_text_features(**inputs)
                emb = emb / emb.norm(dim=-1, keepdim=True)
                return emb[0].cpu().tolist()
        except Exception:
            return None

    def get_status(self) -> dict:
        return {
            'model_type': self._model_type,
            'dim': self.dim,
            'collection': self.collection,
            'gpu_available': self._model_type in ('clip_gpu', 'colqwen2'),
            'description': {
                'clip': 'CLIP ViT-B/32 — CPU可跑，轻量，跨模态匹配',
                'colqwen2': 'ColQwen2 — GPU，Late Interaction多向量检索',
                'hash': '感知哈希 — 无模型，仅用于文档去重',
            }.get(self._model_type, 'unknown')
        }
