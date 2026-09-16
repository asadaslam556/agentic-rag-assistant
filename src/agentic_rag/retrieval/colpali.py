"""ColPali-family encoders for page images.

ColPali treats a page as an image and embeds it with a vision-language
model into one vector per image patch, then retrieves with ColBERT-style
late interaction. Nothing is transcribed, so a bar chart, a schematic,
or a table whose meaning is its layout stays retrievable as itself
rather than as somebody's description of it.

The trade is weight. The original ColPali is PaliGemma-3B, and ColQwen2
is Qwen2-VL-2B, which want a GPU and several gigabytes of memory.
ColSmol is the small member of the family and is the one that runs on a
laptop CPU at a sane speed, which is why it is the default here.

Everything is imported lazily and the model name comes from the
environment, so the package stays installable and testable without
torch. Install the extra to use it:

    pip install -e ".[colpali]"
"""

from __future__ import annotations

from agentic_rag.config import Settings

DEFAULT_MODEL = "vidore/colSmol-256M"


class ColPaliEncoder:
    """Wraps a ColVision model as two calls: embed pages, embed a query."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.colpali_model or DEFAULT_MODEL
        self.name = f"colpali:{self.model_name}"
        self._model = None
        self._processor = None

    def _load(self):
        if self._model is not None:
            return
        try:
            import torch
            from colpali_engine.models import ColIdefics3, ColIdefics3Processor
        except ImportError as exc:
            raise RuntimeError(
                "Page-image retrieval needs the colpali extra. Install it with: "
                'pip install -e ".[colpali]"  (this pulls in torch, which is a large '
                "download). Or set VISUAL_RETRIEVER=description to use page descriptions "
                "instead, which needs no extra install."
            ) from exc

        device = self.settings.colpali_device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float32 if device == "cpu" else torch.bfloat16
        self._model = ColIdefics3.from_pretrained(
            self.model_name, torch_dtype=dtype, device_map=device
        ).eval()
        self._processor = ColIdefics3Processor.from_pretrained(self.model_name)

    def embed_pages(self, images: list[bytes]):
        """One (patches, dim) array per page image."""
        import io

        import numpy as np
        import torch
        from PIL import Image

        self._load()
        pil_images = [Image.open(io.BytesIO(raw)).convert("RGB") for raw in images]
        outputs: list[np.ndarray] = []
        batch_size = max(1, self.settings.colpali_batch_size)
        for start in range(0, len(pil_images), batch_size):
            batch = pil_images[start : start + batch_size]
            processed = self._processor.process_images(batch).to(self._model.device)
            with torch.no_grad():
                embeddings = self._model(**processed)
            for row in embeddings:
                outputs.append(row.to(torch.float32).cpu().numpy())
        return outputs

    def embed_query(self, query: str):
        """A (tokens, dim) array for the question."""
        import torch

        self._load()
        processed = self._processor.process_queries([query]).to(self._model.device)
        with torch.no_grad():
            embeddings = self._model(**processed)
        return embeddings[0].to(torch.float32).cpu().numpy()


def build_encoder(settings: Settings) -> ColPaliEncoder | None:
    """An encoder when page-image retrieval is switched on, else None."""
    if (settings.visual_retriever or "description").lower() != "colpali":
        return None
    return ColPaliEncoder(settings)
