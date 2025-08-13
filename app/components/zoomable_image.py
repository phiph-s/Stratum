from typing import Callable, Optional, Dict, Any
import base64

from nicegui.element import Element


class ZoomableImage(Element, component='zoomable_image.vue'):
    """A NiceGUI Element that wraps the <zoomable-image> Vue component."""

    def __init__(
        self,
        *,
        src: str | None = None,
        on_pixel: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        super().__init__()

        # Forward initial props to the Vue component
        if src:
            self._props['src'] = src

        # Register Python-side event handler
        self.on('pixel', on_pixel)

    # ------------------------------------------------------------------
    # Public helper methods (call Vue's defineExpose hooks)
    # ------------------------------------------------------------------
    def set_source(self, src: str, reset=False) -> None:
        """Dynamically load a new image file/URL or SVG content."""
        self.run_method('setSrc', src, reset)

    def set_svg_content(self, svg_content: str, reset=False) -> None:
        """Set SVG content directly as a string."""
        # Create a data URL for the SVG content
        svg_base64 = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
        svg_data_url = f'data:image/svg+xml;base64,{svg_base64}'
        self.set_source(svg_data_url, reset)

    def reset_transform(self) -> None:
        """Reset zoom & pan to initial fit."""
        self.run_method('reset')
