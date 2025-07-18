from typing import Callable, Optional, Dict, Any

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
    def set_source(self, src: str) -> None:
        """Dynamically load a new image file/URL."""
        self.run_method('setSrc', src)

    def reset_transform(self) -> None:
        """Reset zoom & pan to initial fit."""
        self.run_method('reset')
