import "Sortable";

export default {
  template: `
    <div class="filament-list-container">
      <div v-if="internalFilaments.length === 0" class="text-gray-500">
        <strong>No filaments added</strong>
      </div>
      <div v-else ref="sortableContainer" class="filament-items">
        <div 
          v-for="(filament, displayIdx) in reversedFilaments" 
          :key="filament.instance_id"
          :data-instance-id="filament.instance_id"
          class="filament-item w-full mb-2"
          :class="getRowClasses(filament)"
          :style="getRowStyle(filament)"
        >
          <!-- Drag handle -->
          <div class="drag-handle flex-shrink-0 cursor-move p-1" style="display: flex; align-items: center;">
            <q-icon name="drag_indicator" class="text-current opacity-60" />
          </div>

          <!-- Main content area -->
          <div class="flex-grow gap-0 min-w-0" style="display: flex; flex-direction: column;">
            <!-- First row: Name with context menu -->
            <div class="items-center gap-2 w-full justify-between" style="display: flex;">
              <div 
                class="text-sm font-semibold w-32 truncate" 
                :title="getTooltip(filament)"
              >
                {{ getDisplayName(filament) }}
              </div>
              <!-- Right side: Context menu - fixed size -->
              <q-btn 
                icon="more_vert" 
                flat 
                round 
                size="sm"
                :class="getRowClasses(filament) + ' flex-shrink-0'"
                style="min-width: 32px;"
              >
                <q-menu>
                  <q-list>
                    <q-item clickable v-close-popup @click="removeFilament(filament.instance_id)">
                      <q-item-section>Remove</q-item-section>
                    </q-item>
                  </q-list>
                </q-menu>
              </q-btn>
            </div>

            <!-- Second row: Slider with icons -->
            <div v-if="displayIdx === reversedFilaments.length - 1" class="items-center gap-1 w-full flex-nowrap" style="display: flex;">
              <q-icon name="vertical_align_bottom" class="text-xs flex-shrink-0" style="padding-right: 4px;" />
              <span class="text-xs" title="The layers of the bottom layer is set in the export settings">
                First layer
              </span>
            </div>
            <div v-else class="items-center gap-1 w-full flex-nowrap" style="display: flex;">
              <q-slider
                :model-value="filament.max_layers"
                :min="1"
                :max="20"
                :color="getSliderColor(filament)"
                :label-text-color="getSliderLabelColor(filament)"
                dense
                label
                markers
                class="flex-1 min-w-0"
                style="margin-right: 4px; font-size: 0.75rem;"
                @update:model-value="updateMaxLayers(filament.instance_id, $event)"
              />
              <span class="text-xs flex-shrink-0 text-center">{{ filament.max_layers }}</span>
              <q-icon name="layers" class="text-xs flex-shrink-0" style="padding-right: 8px;" />
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  props: {
    filaments: {
      type: Array,
      default: () => []
    }
  },
  data() {
    return {
      sortable: null,
      internalFilaments: [],
      managerColors: {}
    };
  },
  computed: {
    reversedFilaments() {
      // Reverse for display (top is last in array)
      return [...this.internalFilaments].reverse();
    }
  },
  watch: {
    filaments: {
      handler(newFilaments) {
        // Only update if different from internal state
        if (JSON.stringify(newFilaments) !== JSON.stringify(this.internalFilaments)) {
          this.internalFilaments = this.processFilaments([...newFilaments]);
        }
      },
      immediate: true,
      deep: true
    }
  },
  mounted() {
    this.initSortable();
  },
  updated() {
    this.initSortable();
  },
  beforeUnmount() {
    if (this.sortable) {
      this.sortable.destroy();
    }
  },
  methods: {
    processFilaments(filaments) {
      return filaments.map(filament => {
        // Ensure instance_id exists
        if (!filament.instance_id) {
          filament.instance_id = this.generateInstanceId();
        }

        // Get current color from manager if available, otherwise use copied_data
        const managerId = filament.id;
        let currentColor = filament.copied_data?.color || '#000000';
        let currentName = filament.copied_data?.name || 'Unnamed';
        let currentTdValue = filament.copied_data?.td_value || 0.5;

        if (managerId && this.managerColors[managerId]) {
          currentColor = this.managerColors[managerId];
        }

        return {
          ...filament,
          currentColor,
          currentName,
          currentTdValue,
          max_layers: filament.max_layers || 5
        };
      });
    },

    generateInstanceId() {
      return 'instance_' + Math.random().toString(36).substr(2, 9);
    },

    initSortable() {
      if (this.sortable) {
        this.sortable.destroy();
      }
      
      const container = this.$refs.sortableContainer;
      if (container && this.internalFilaments.length > 0) {
        this.sortable = new Sortable(container, {
          animation: 150,
          ghostClass: 'sortable-ghost',
          chosenClass: 'sortable-chosen',
          dragClass: 'sortable-drag',
          handle: '.drag-handle',
          onEnd: (evt) => {
            const oldIndex = evt.oldIndex;
            const newIndex = evt.newIndex;
            
            // Reorder in reversed array, then unreverse
            const reversed = [...this.internalFilaments].reverse();
            const [movedItem] = reversed.splice(oldIndex, 1);
            reversed.splice(newIndex, 0, movedItem);

            this.internalFilaments = reversed.reverse();
            this.syncState();
          }
        });
      }
    },

    getRowClasses(filament) {
      let classes = 'items-center gap-1 p-1 rounded';
      if (this.isBright(filament.currentColor)) {
        classes += ' text-black';
      } else {
        classes += ' text-white border border-gray-400';
      }
      return classes;
    },

    getRowStyle(filament) {
      return {
        backgroundColor: filament.currentColor || '#000000',
        display: 'flex',
        width: '100%'
      };
    },

    getDisplayName(filament) {
      const isProjectSpecific = !filament.id;
      const prefix = isProjectSpecific ? "* " : "";
      return prefix + (filament.currentName || 'Unnamed');
    },

    getTooltip(filament) {
      let tooltip = filament.currentName || 'Unnamed';
      if (!filament.id) {
        tooltip += " (not in library)";
      }
      return tooltip;
    },

    getSliderColor(filament) {
      return this.isBright(filament.currentColor) ? 'black' : 'white';
    },

    getSliderLabelColor(filament) {
      return this.isBright(filament.currentColor) ? 'white' : 'black';
    },

    isBright(colorHex) {
      try {
        const r = parseInt(colorHex.slice(1, 3), 16);
        const g = parseInt(colorHex.slice(3, 5), 16);
        const b = parseInt(colorHex.slice(5, 7), 16);
        return (r + g + b) / 3 > 128;
      } catch {
        return false;
      }
    },

    removeFilament(instanceId) {
      this.internalFilaments = this.internalFilaments.filter(f => f.instance_id !== instanceId);
      this.syncState();
    },

    updateMaxLayers(instanceId, value) {
      const filament = this.internalFilaments.find(f => f.instance_id === instanceId);
      if (filament) {
        filament.max_layers = parseInt(value);
        this.syncState();
      }
    },

    updateManagerColors(colorMap) {
      this.managerColors = colorMap;
      // Reprocess filaments to update colors
      this.internalFilaments = this.processFilaments(this.internalFilaments);
      this.syncState();
    },

    syncState() {
      // Emit the current state to keep parent in sync
      this.$emit('sync-state', [...this.internalFilaments]);
    }
  }
};
