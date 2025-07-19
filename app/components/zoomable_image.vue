<template>
  <div
    ref="container"
    class="viewer-container w-full h-full overflow-hidden select-none relative"
    :style="containerStyle"
    @wheel="onWheel"
    @mousedown="onMouseDown"
    @click="onClick"
  >
    <img
      ref="img"
      style="max-width: none; max-height: none;"
      :src="src"
      :style="imgStyle"
      @load="onImgLoad"
      draggable="false"
    />
    <canvas ref="canvas" style="display:none"></canvas>
  </div>
</template>

<script>
export default {
  name: 'ZoomableImage',
  props: {
    src: { type: String, required: true },
  },
  data() {
    return {
      naturalSize: { w: 0, h: 0 },
      scale: 1,
      minScale: 0.1,
      maxScale: 10,
      translate: { x: 0, y: 0 },
      dragging: false,
      lastMouse: { x: 0, y: 0 },
    };
  },
  computed: {
    // Background checkerboard pattern
    containerStyle() {
      return {
        backgroundColor: '#8a8a8a',
        backgroundImage:
          'radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.2) 70%, rgba(0,0,0,0.4) 100%), ' +
          'linear-gradient(45deg, #666 25%, transparent 25%, transparent 75%, #666 75%, #666), ' +
          'linear-gradient(45deg, #666 25%, transparent 25%, transparent 75%, #666 75%, #666)',
        backgroundSize: '100% 100%, 20px 20px, 20px 20px',
        backgroundPosition: '0 0, 0 0, 10px 10px',
      };
    },
    // Transform & sizing for <img>
    imgStyle() {
      return {
        transform: `translate(${this.translate.x}px, ${this.translate.y}px) scale(${this.scale})`,
        transformOrigin: '0 0',
        userSelect: 'none',
        pointerEvents: 'none',
      };
    },
  },
  watch: {
    // When src is changed externally via prop, delegate to setSrc so we keep state
    src(newVal) {
      this.setSrc(newVal);
    },
  },
  mounted() {
    if (this.$refs.img.complete) this.onImgLoad();
  },
  methods: {
    /* ---------------------------------------
     * Utility helpers
     * -------------------------------------*/
    clamp(v, min, max) {
      return Math.min(Math.max(v, min), max);
    },
    redrawCanvas() {
      const ctx = this.$refs.canvas.getContext('2d');
      ctx.clearRect(0, 0, this.naturalSize.w, this.naturalSize.h);
      ctx.drawImage(
        this.$refs.img,
        0,
        0,
        this.naturalSize.w,
        this.naturalSize.h,
      );
    },
    computeClickData(evt) {
      const rect = this.$refs.container.getBoundingClientRect();
      const cx = evt.clientX - rect.left;
      const cy = evt.clientY - rect.top;
      const ix = (cx - this.translate.x) / this.scale;
      const iy = (cy - this.translate.y) / this.scale;
      if (
        ix < 0 ||
        iy < 0 ||
        ix >= this.naturalSize.w ||
        iy >= this.naturalSize.h
      )
        return null;
      const pixel = this.$refs.canvas
        .getContext('2d')
        .getImageData(Math.floor(ix), Math.floor(iy), 1, 1).data;
      return {
        coords: { x: Math.floor(ix), y: Math.floor(iy) },
        rgb: { r: pixel[0], g: pixel[1], b: pixel[2], a: pixel[3] },
      };
    },
    /* ---------------------------------------
     * Fitting & centering
     * -------------------------------------*/
    fitImage() {
      const rect = this.$refs.container.getBoundingClientRect();
      // If the container has not been laid out yet (width/height 0) defer until next tick
      if (!rect.width || !rect.height) {
        this.$nextTick(this.fitImage);
        return;
      }

      const paddingX = rect.width * 0.10;
      const paddingY = rect.height * 0.10;
      const innerW = rect.width - paddingX * 2;
      const innerH = rect.height - paddingY * 2;

      const scaleX = innerW / this.naturalSize.w;
      const scaleY = innerH / this.naturalSize.h;
      this.scale = Math.min(scaleX, scaleY, 1);

      // center inside the padded area
      this.translate.x = paddingX + (innerW - this.naturalSize.w * this.scale) / 2;
      this.translate.y = paddingY + (innerH - this.naturalSize.h * this.scale) / 2;
    },
    /* ---------------------------------------
     * Lifecycle
     * -------------------------------------*/
    onImgLoad() {
      this.naturalSize = {
        w: this.$refs.img.naturalWidth,
        h: this.$refs.img.naturalHeight,
      };
      this.$refs.canvas.width = this.naturalSize.w;
      this.$refs.canvas.height = this.naturalSize.h;
      this.redrawCanvas();
      // If view is untouched (initial or after reset), re‑center
      if (
        this.scale === 1 &&
        this.translate.x === 0 &&
        this.translate.y === 0
      ) {
        this.fitImage();
      }
    },
    /* ---------------------------------------
     * Interaction handlers
     * -------------------------------------*/
    onWheel(evt) {
      evt.preventDefault();
      const delta = -evt.deltaY || evt.wheelDelta || -evt.detail;
      const zoom = delta > 0 ? 1.1 : 0.9;
      const newScale = this.clamp(
        this.scale * zoom,
        this.minScale,
        this.maxScale,
      );
      const rect = this.$refs.container.getBoundingClientRect();
      const cx = evt.clientX - rect.left;
      const cy = evt.clientY - rect.top;
      this.translate.x = cx - ((cx - this.translate.x) / this.scale) * newScale;
      this.translate.y = cy - ((cy - this.translate.y) / this.scale) * newScale;
      this.scale = newScale;
    },
    onMouseDown(evt) {
      this.dragging = true;
      this.lastMouse = { x: evt.clientX, y: evt.clientY };
      window.addEventListener('mousemove', this.onMouseMove);
      window.addEventListener('mouseup', this.onMouseUp);
    },
    onMouseMove(evt) {
      if (!this.dragging) return;
      const dx = evt.clientX - this.lastMouse.x;
      const dy = evt.clientY - this.lastMouse.y;
      this.translate.x += dx;
      this.translate.y += dy;
      this.lastMouse = { x: evt.clientX, y: evt.clientY };
    },
    onMouseUp() {
      this.dragging = false;
      window.removeEventListener('mousemove', this.onMouseMove);
      window.removeEventListener('mouseup', this.onMouseUp);
    },
    onClick(evt) {
      const data = this.computeClickData(evt);
      if (data) {
        this.$refs.container.dispatchEvent(
          new CustomEvent('pixel', { detail: data }),
        );
      }
    },
    /* ---------------------------------------
     * Methods callable from Python side
     * -------------------------------------*/
    setSrc(newSrc, reset = false) {
      // If the caller wants a full reset, wait for the load event
      if (reset) {
        const img = this.$refs.img;

        // Use { once: true } so the listener cleans itself up automatically
        const onLoad = () => {
          this.reset();              // restore scale/translate and refit
        };
        img.addEventListener('load', onLoad, { once: true });
      }

      // Trigger the load
      this.$refs.img.src = newSrc;
    },
    reset() {
      this.scale = 1;
      this.translate = { x: 0, y: 0 };
      this.fitImage();
    }
  },
};
</script>

<style scoped>
.viewer-container img {
  display: block;
}
</style>
