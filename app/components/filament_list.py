from typing import Callable, Optional, List, Dict, Any
from nicegui.element import Element


class FilamentList(Element,
                   component='filament_list.js',
                   dependencies=['node_modules/sortablejs/Sortable.min.js']):
    """A NiceGUI Element that wraps the <filament-list> Vue component."""

    def __init__(
        self,
        *,
        filaments: List[Dict[str, Any]] = None,
        on_move: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_remove: Optional[Callable[[int], None]] = None,
        on_update_max_layers: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_reorder: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        super().__init__()

        # Forward initial props to the Vue component
        if filaments is not None:
            self._props['filaments'] = filaments
        else:
            self._props['filaments'] = []

        # Register Python-side event handlers
        self.on('move', on_move)
        self.on('remove', on_remove)
        self.on('update-max-layers', on_update_max_layers)
        self.on('reorder', on_reorder)

    # ------------------------------------------------------------------
    # Public helper methods
    # ------------------------------------------------------------------
    def update_filaments(self, filaments: List[Dict[str, Any]]) -> None:
        """Update the filaments list."""
        self._props['filaments'] = filaments
        self.update()
