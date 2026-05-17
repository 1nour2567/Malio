/* ================================================================
   ColorExtractor — get dominant color from album cover <img>
   Uses canvas pixel sampling + simple frequency clustering.
   ================================================================ */

function extractDominantColor (imgEl) {
  if (!imgEl || !imgEl.complete || !imgEl.naturalWidth) return null;

  try {
    const canvas = document.createElement('canvas');
    const size = 60;  /* sample at 60x60 = 3600 pixels, fast enough */
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(imgEl, 0, 0, size, size);

    const data = ctx.getImageData(0, 0, size, size).data;
    const colorMap = {};
    const step = 4;  /* quantize: group similar colors */

    for (let i = 0; i < data.length; i += 4 * step) {
      const r = Math.round(data[i] / 32) * 32;
      const g = Math.round(data[i + 1] / 32) * 32;
      const b = Math.round(data[i + 2] / 32) * 32;
      /* skip very dark (black bg) and very light (white bg) */
      const brightness = (r + g + b) / 3;
      if (brightness < 15 || brightness > 240) continue;
      const key = r + ',' + g + ',' + b;
      colorMap[key] = (colorMap[key] || 0) + 1;
    }

    let best = null, bestCount = 0;
    for (const [key, count] of Object.entries(colorMap)) {
      if (count > bestCount) { best = key; bestCount = count; }
    }

    if (!best) return null;
    const [r, g, b] = best.split(',').map(Number);
    return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
  } catch (e) {
    return null;  /* cross-origin image, fallback to mood color */
  }
}

/* expose globally */
window.extractDominantColor = extractDominantColor;
