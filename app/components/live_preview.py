from typing import Callable, List
import asyncio, io
from nicegui import ui

class LivePreviewController:
    """Manages live preview loop; pulls current inputs via callbacks from main."""
    def __init__(self, *, get_image: Callable[[], object], get_filaments: Callable[[], List[dict]], get_layer_height: Callable[[], float], compute_shades: Callable, segment_image: Callable, on_render: Callable[[bytes, [], []], None], on_status_live: Callable[[], None], on_after_change: Callable[[], None]):
        self.get_image = get_image
        self.get_filaments = get_filaments
        self.get_layer_height = get_layer_height
        self.compute_shades = compute_shades
        self.segment_image = segment_image
        self.on_render = on_render
        self.on_status_live = on_status_live
        self.on_after_change = on_after_change

        self.enabled = True
        self._updating = False
        self._restart_pending = False

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if enabled:
            asyncio.create_task(self.update())

    async def update(self):
        if self.get_image() is None or len(self.get_filaments()) < 2:
            return
        if self._updating:
            self._restart_pending = True
            return
        self._updating = True
        while True:
            self._restart_pending = False
            try:
                filaments = self.get_filaments()
                colors, max_layers, td_values = [], [], []
                for f in filaments:
                    data = f.get('copied_data', {})
                    color = data.get('color', '#000000')
                    rgb = tuple(int(color[i:i+2], 16) for i in (1,3,5))
                    colors.append(rgb)
                    max_layers.append(f.get('max_layers', data.get('max_layers', 5)))
                    td_values.append(data.get('td_value', 0.5))

                def compute():
                    shades = self.compute_shades(colors, td_values, max_layers, float(self.get_layer_height()))
                    segmented = self.segment_image(self.get_image(), shades)
                    return segmented, shades

                loop = asyncio.get_running_loop()
                segmented, shades = await loop.run_in_executor(None, compute)

                buf = io.BytesIO(); segmented.save(buf, format='PNG')
                self.on_render(buf.getvalue(), shades, colors)
                self.on_status_live()
                self.on_after_change()
            except Exception as e:
                print(f'Error in live preview: {e}')
            if not self._restart_pending:
                break
        self._updating = False
