from typing import Callable
from nicegui import ui
from app.components.zoomable_image import ZoomableImage  # adjust if your import path differs
import io, base64
from PIL import Image

class ImageViewer:
    """Owns placeholder/upload + the ZoomableImage, and exposes helpers to set image content."""
    def __init__(self, *, on_pixel: Callable[[dict], None], on_upload_image: Callable[[Image.Image], None]):
        self.on_pixel = on_pixel
        self.on_upload_image = on_upload_image

        self.placeholder = None
        self.upload = None
        self.viewer = None

        self._build()

    def _build(self):
        self.placeholder = ui.column().classes('items-center justify-center h-full gap-4 w-80').style('display: flex;')
        with self.placeholder:
            ui.markdown('**No image loaded**').classes('text-gray-500')
            self.upload = ui.upload(max_files=1, auto_upload=True, on_upload=self._handle_upload).props('label="Load Image" accept="image/*"').classes('w-full')
            infotext_start = ui.column().classes('absolute bottom-4 left-80 text-gray-500 text-sm')
            with infotext_start:
                ui.icon('arrow_right').classes('text-gray-500 text-2xl')

        self.viewer = ZoomableImage(src='/static/photo.jpg', on_pixel=self._forward_pixel).classes('w-full h-full')

    # ---- API for setting image content ---------------------------------
    def show_placeholder(self, show: bool):
        self.placeholder.visible = show
        self.viewer.visible = not show

    def set_pil(self, img: Image.Image, *, reset=False):
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        data = base64.b64encode(buf.getvalue()).decode()
        self.viewer.set_source(f'data:image/png;base64,{data}', reset)

    def set_max_size(self, cm: float):
        self.viewer.set_max_size(cm)

    def reset_transform(self):
        self.viewer.reset_transform()

    # ---- internals ------------------------------------------------------
    def _forward_pixel(self, e):
        self.on_pixel(e)

    def _handle_upload(self, files):
        img = Image.open(files.content).convert('RGBA')
        self.on_upload_image(img)
        self.upload.reset()
