from typing import Callable, Optional, List, Dict, Any
from nicegui.element import Element
import uuid


class FilamentList(Element,
                   component='filament_list.js',
                   dependencies=['node_modules/sortablejs/Sortable.min.js']):
    """A NiceGUI Element that wraps the <filament-list> Vue component."""

    def __init__(
        self,
        *,
        filaments: List[Dict[str, Any]] = None,
        filament_manager=None,
        on_change: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    ) -> None:
        super().__init__()

        # Store reference to filament manager for color sync
        self.filament_manager = filament_manager
        self.on_change_callback = on_change

        # Ensure each filament has an instance_id for tracking
        if filaments is None:
            filaments = []

        for filament in filaments:
            if 'instance_id' not in filament:
                filament['instance_id'] = str(uuid.uuid4())

        # Forward initial props to the Vue component
        self._props['filaments'] = filaments

        # Register event handler for full state synchronization
        self.on('sync-state', self._handle_sync_state)

    def _handle_sync_state(self, e):
        """Handle full state synchronization from Vue component"""
        new_filaments = e.args

        # Ensure all filaments have instance_ids
        for filament in new_filaments:
            if 'instance_id' not in filament:
                filament['instance_id'] = str(uuid.uuid4())

        # Update our props
        self._props['filaments'] = new_filaments

        # Notify parent about the change
        if self.on_change_callback:
            self.on_change_callback(new_filaments)

    def update_filaments(self, filaments: List[Dict[str, Any]]) -> None:
        """Update the filaments list from external source"""
        # Ensure each filament has an instance_id
        for filament in filaments:
            if 'instance_id' not in filament:
                filament['instance_id'] = str(uuid.uuid4())

        self._props['filaments'] = filaments
        self.update()

    def get_manager_colors(self) -> Dict[str, str]:
        """Get current colors from filament manager for sync"""
        if not self.filament_manager:
            return {}

        color_map = {}
        for filament in self.filament_manager.saved_filaments:
            color_map[filament['id']] = filament['color']
        return color_map

    def sync_manager_colors(self) -> None:
        """Sync current manager colors to Vue component"""
        color_map = self.get_manager_colors()
        self.run_method('updateManagerColors', color_map)

    def get_current_filaments(self) -> List[Dict[str, Any]]:
        """Get current filaments state from Vue component"""
        return self._props.get('filaments', [])
