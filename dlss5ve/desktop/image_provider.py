from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


class PreviewImageProvider(QQuickImageProvider):
    """Thread-safe memory-backed QML image provider with bounded LRU storage."""

    def __init__(self, max_bytes: int = 384 * 1024 * 1024) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._lock = threading.RLock()
        self._images: OrderedDict[str, QImage] = OrderedDict()
        self._sizes: dict[str, int] = {}
        self._bytes = 0
        self._max_bytes = max(32 * 1024 * 1024, int(max_bytes))

    @staticmethod
    def _image_bytes(image: QImage) -> int:
        try:
            return int(image.sizeInBytes())
        except Exception:
            return int(image.width() * image.height() * max(1, image.depth() // 8))

    def set_image(self, image_id: str, image_data: Any) -> None:
        qimg = self._to_qimage(image_data)
        if qimg is None or qimg.isNull():
            return
        clean_id = image_id.split("?", 1)[0]
        with self._lock:
            old = self._images.pop(clean_id, None)
            if old is not None:
                self._bytes -= self._sizes.pop(clean_id, 0)
            self._images[clean_id] = qimg
            size = self._image_bytes(qimg)
            self._sizes[clean_id] = size
            self._bytes += size
            while self._bytes > self._max_bytes and len(self._images) > 1:
                key, _ = self._images.popitem(last=False)
                self._bytes -= self._sizes.pop(key, 0)

    def clear(self, image_id: str | None = None) -> None:
        with self._lock:
            if image_id is not None:
                clean_id = image_id.split("?", 1)[0]
                self._images.pop(clean_id, None)
                self._bytes -= self._sizes.pop(clean_id, 0)
            else:
                self._images.clear()
                self._sizes.clear()
                self._bytes = 0

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        clean_id = image_id.split("?", 1)[0]
        with self._lock:
            img = self._images.get(clean_id)
            if img is not None and not img.isNull():
                self._images.move_to_end(clean_id)
                size.setWidth(img.width())
                size.setHeight(img.height())
                if requested_size.isValid() and requested_size.width() > 0 and requested_size.height() > 0:
                    return img.scaled(requested_size)
                return img
        placeholder = QImage(1, 1, QImage.Format.Format_RGBA8888)
        placeholder.fill(0)
        size.setWidth(1)
        size.setHeight(1)
        return placeholder

    @staticmethod
    def _to_qimage(data: Any) -> QImage | None:
        if data is None:
            return None
        if isinstance(data, QImage):
            return data.copy()
        if isinstance(data, (str, Path)):
            path_str = str(data).strip()
            if path_str and Path(path_str).is_file():
                img = QImage(path_str)
                if not img.isNull():
                    return img
                try:
                    with Image.open(path_str) as pil_img:
                        return PreviewImageProvider._pil_to_qimage(pil_img)
                except Exception:
                    return None
            return None
        if isinstance(data, Image.Image):
            return PreviewImageProvider._pil_to_qimage(data)
        if isinstance(data, np.ndarray):
            return PreviewImageProvider._numpy_to_qimage(data)
        return None

    @staticmethod
    def _pil_to_qimage(pil_img: Image.Image) -> QImage:
        converted = pil_img if pil_img.mode == "RGBA" else pil_img.convert("RGBA")
        data = converted.tobytes("raw", "RGBA")
        return QImage(data, converted.width, converted.height, QImage.Format.Format_RGBA8888).copy()

    @staticmethod
    def _numpy_to_qimage(arr: np.ndarray) -> QImage:
        if arr.ndim == 2:
            h, w = arr.shape
            return QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        if arr.ndim == 3:
            h, w, channels = arr.shape
            if channels == 3:
                return QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
            if channels == 4:
                return QImage(arr.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
        return QImage()
