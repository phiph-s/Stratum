<template>
  <div
    ref="container"
    class="w-full h-full overflow-hidden select-none relative"
    @wheel="onWheel"
    @mousedown="onMouseDown"
    @click="onClick"
  >
    <img
      ref="img"
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
    maxWidth: { type: [String, Number], default: undefined },
    maxHeight: { type: [String, Number], default: undefined },
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
    imgStyle() {
      return {
        transform: `translate(${this.translate.x}px, ${this.translate.y}px) scale(${this.scale})`,
        transformOrigin: '0 0',
        maxWidth: this.maxWidth ?? 'none',
        maxHeight: this.maxHeight ?? 'none',
        userSelect: 'none',
        pointerEvents: 'none',
      };
    },
  },
  watch: {
    src(newVal) {
      this.setSrc(newVal);
    },
  },
  mounted() {
    if (this.$refs.img.complete) this.onImgLoad();
  },
  methods: {
    /** Utils */
    clamp(v, min, max) { return Math.min(Math.max(v, min), max); },
    redrawCanvas() {
      const ctx = this.$refs.canvas.getContext('2d');
      ctx.clearRect(0, 0, this.naturalSize.w, this.naturalSize.h);
      ctx.drawImage(this.$refs.img, 0, 0, this.naturalSize.w, this.naturalSize.h);
    },
    computeClickData(evt) {
      const rect = this.$refs.container.getBoundingClientRect();
      const cx = evt.clientX - rect.left;
      const cy = evt.clientY - rect.top;
      const ix = (cx - this.translate.x) / this.scale;
      const iy = (cy - this.translate.y) / this.scale;
      if (ix < 0 || iy < 0 || ix >= this.naturalSize.w || iy >= this.naturalSize.h) return null;
      const pixel = this.$refs.canvas.getContext('2d').getImageData(Math.floor(ix), Math.floor(iy), 1, 1).data;
      return {
        coords: { x: Math.floor(ix), y: Math.floor(iy) },
        rgb: { r: pixel[0], g: pixel[1], b: pixel[2], a: pixel[3] },
      };
    },
    fitImage() {
      const rect = this.$refs.container.getBoundingClientRect();
      const scaleX = rect.width / this.naturalSize.w;
      const scaleY = rect.height / this.naturalSize.h;
      this.scale = Math.min(scaleX, scaleY, 1);
      this.translate.x = (rect.width - this.naturalSize.w * this.scale) / 2;
      this.translate.y = (rect.height - this.naturalSize.h * this.scale) / 2;
    },
    /** Lifecycle-related */
    onImgLoad() {
      this.naturalSize = { w: this.$refs.img.naturalWidth, h: this.$refs.img.naturalHeight };
      this.$refs.canvas.width  = this.naturalSize.w;
      this.$refs.canvas.height = this.naturalSize.h;
      this.redrawCanvas();

      // auto-fit only on first load or after explicit reset
      if (this.scale === 1 && this.translate.x === 0 && this.translate.y === 0) {
        this.fitImage();
      }
    },
    /** Interaction handlers */
    onWheel(evt) {
      evt.preventDefault();
      const delta = -evt.deltaY || evt.wheelDelta || -evt.detail;
      const zoom = delta > 0 ? 1.1 : 0.9;
      const newScale = this.clamp(this.scale * zoom, this.minScale, this.maxScale);
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
        this.$refs.container.dispatchEvent(new CustomEvent('pixel', { detail: data }));
      }
    },
    /** Methods callable from Python side via run_method */
    setSrc(newSrc) {
      this.$refs.img.src = newSrc;
      // wait for load event to redraw
    },
    reset() {
      this.scale = 1;
      this.translate = { x: 0, y: 0 };
      if (this.$refs.img.complete) this.fitImage();
    },
  },
};
</script>

<style scoped>
img {
  display: block;
}
</style>