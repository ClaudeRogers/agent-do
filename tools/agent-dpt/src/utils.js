// DPT Shared Utilities — Color Math, Geometry, DOM Traversal
// These run in the browser context via page.evaluate()

const DPT_UTILS = {

  // ─── Color Parsing ───────────────────────────────────────────────

  _unparseableColors: new Map(),

  _recordUnparseableColor(str) {
    const value = String(str || '').trim();
    if (!value) return;
    this._unparseableColors.set(value, (this._unparseableColors.get(value) || 0) + 1);
  },

  colorParseDiagnostics() {
    const entries = Array.from(this._unparseableColors.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return {
      unparseable_count: entries.reduce((sum, entry) => sum + entry[1], 0),
      unique_unparseable: entries.length,
      samples: entries.slice(0, 10).map(([value, occurrences]) =>
        occurrences > 1 ? `${value} (${occurrences} uses)` : value
      )
    };
  },

  _clampChannel(value) {
    return Math.round(Math.max(0, Math.min(1, value)) * 255);
  },

  _parseAlpha(value) {
    if (value == null || value === '') return 1;
    const token = String(value).trim();
    const parsed = parseFloat(token);
    if (!Number.isFinite(parsed)) return null;
    return Math.max(0, Math.min(1, token.endsWith('%') ? parsed / 100 : parsed));
  },

  _parseRgbChannel(value) {
    const token = String(value).trim();
    const parsed = parseFloat(token);
    if (!Number.isFinite(parsed)) return null;
    return Math.max(0, Math.min(255, token.endsWith('%') ? parsed * 2.55 : parsed));
  },

  _parseUnitInterval(value, percentScale = 1) {
    const token = String(value).trim();
    const parsed = parseFloat(token);
    if (!Number.isFinite(parsed)) return null;
    return token.endsWith('%') ? (parsed / 100) * percentScale : parsed;
  },

  _parseHue(value) {
    const token = String(value).trim().toLowerCase();
    const parsed = parseFloat(token);
    if (!Number.isFinite(parsed)) return null;
    if (token.endsWith('turn')) return parsed * 360;
    if (token.endsWith('grad')) return parsed * 0.9;
    if (token.endsWith('rad')) return parsed * (180 / Math.PI);
    return parsed;
  },

  _linearToSrgb(value) {
    return value <= 0.0031308
      ? 12.92 * value
      : 1.055 * Math.pow(value, 1 / 2.4) - 0.055;
  },

  _srgbToLinear(value) {
    return value <= 0.04045
      ? value / 12.92
      : Math.pow((value + 0.055) / 1.055, 2.4);
  },

  _fromLinearSrgb(r, g, b, a) {
    return {
      r: this._clampChannel(this._linearToSrgb(r)),
      g: this._clampChannel(this._linearToSrgb(g)),
      b: this._clampChannel(this._linearToSrgb(b)),
      a
    };
  },

  parseColor(str) {
    if (!str) return null;
    const raw = String(str).trim();
    const lower = raw.toLowerCase();
    if (!raw || lower === 'transparent') return null;

    const hex = lower.match(/^#([0-9a-f]{3,8})$/i);
    if (hex) {
      let value = hex[1];
      if (value.length === 3 || value.length === 4) {
        value = value.split('').map(char => char + char).join('');
      }
      if (value.length === 6 || value.length === 8) {
        return {
          r: parseInt(value.slice(0, 2), 16),
          g: parseInt(value.slice(2, 4), 16),
          b: parseInt(value.slice(4, 6), 16),
          a: value.length === 8 ? parseInt(value.slice(6, 8), 16) / 255 : 1
        };
      }
    }

    const rgb = lower.match(/^rgba?\((.*)\)$/);
    if (rgb) {
      const commaSyntax = rgb[1].includes(',');
      let channels;
      let alphaToken;
      if (commaSyntax) {
        const parts = rgb[1].split(',').map(part => part.trim());
        channels = parts.slice(0, 3);
        alphaToken = parts[3];
      } else {
        const slashParts = rgb[1].split('/').map(part => part.trim());
        channels = slashParts[0].split(/\s+/);
        alphaToken = slashParts[1];
      }
      if (channels.length === 3) {
        const parsed = channels.map(channel => this._parseRgbChannel(channel));
        const alpha = this._parseAlpha(alphaToken);
        if (parsed.every(Number.isFinite) && alpha != null) {
          if (alpha === 0) return null;
          return {
            r: Math.round(parsed[0]),
            g: Math.round(parsed[1]),
            b: Math.round(parsed[2]),
            a: alpha
          };
        }
      }
      this._recordUnparseableColor(raw);
      return null;
    }

    const hsl = lower.match(/^hsla?\((.*)\)$/);
    if (hsl) {
      const commaSyntax = hsl[1].includes(',');
      let channels;
      let alphaToken;
      if (commaSyntax) {
        const parts = hsl[1].split(',').map(part => part.trim());
        channels = parts.slice(0, 3);
        alphaToken = parts[3];
      } else {
        const slashParts = hsl[1].split('/').map(part => part.trim());
        channels = slashParts[0].split(/\s+/);
        alphaToken = slashParts[1];
      }
      if (channels.length === 3) {
        const hue = this._parseHue(channels[0]);
        const saturation = this._parseUnitInterval(channels[1]);
        const lightness = this._parseUnitInterval(channels[2]);
        const alpha = this._parseAlpha(alphaToken);
        if ([hue, saturation, lightness].every(Number.isFinite) && alpha != null) {
          const normalizedHue = ((hue % 360) + 360) % 360;
          const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
          const x = chroma * (1 - Math.abs((normalizedHue / 60) % 2 - 1));
          const offset = lightness - chroma / 2;
          let red = 0;
          let green = 0;
          let blue = 0;
          if (normalizedHue < 60) [red, green, blue] = [chroma, x, 0];
          else if (normalizedHue < 120) [red, green, blue] = [x, chroma, 0];
          else if (normalizedHue < 180) [red, green, blue] = [0, chroma, x];
          else if (normalizedHue < 240) [red, green, blue] = [0, x, chroma];
          else if (normalizedHue < 300) [red, green, blue] = [x, 0, chroma];
          else [red, green, blue] = [chroma, 0, x];
          return {
            r: this._clampChannel(red + offset),
            g: this._clampChannel(green + offset),
            b: this._clampChannel(blue + offset),
            a: alpha
          };
        }
      }
      this._recordUnparseableColor(raw);
      return null;
    }

    const oklch = lower.match(/^oklch\((.*)\)$/);
    if (oklch) {
      const slashParts = oklch[1].split('/').map(part => part.trim());
      const channels = slashParts[0].split(/\s+/);
      const alpha = this._parseAlpha(slashParts[1]);
      if (channels.length === 3 && alpha != null) {
        const lightness = this._parseUnitInterval(channels[0]);
        // CSS Color 4 maps 100% chroma to 0.4 for OKLCH.
        const chroma = this._parseUnitInterval(channels[1], 0.4);
        const hue = this._parseHue(channels[2]);
        if ([lightness, chroma, hue].every(Number.isFinite)) {
          const radians = hue * Math.PI / 180;
          const a = chroma * Math.cos(radians);
          const b = chroma * Math.sin(radians);
          const lPrime = lightness + 0.3963377774 * a + 0.2158037573 * b;
          const mPrime = lightness - 0.1055613458 * a - 0.0638541728 * b;
          const sPrime = lightness - 0.0894841775 * a - 1.2914855480 * b;
          const l = lPrime ** 3;
          const m = mPrime ** 3;
          const s = sPrime ** 3;
          return this._fromLinearSrgb(
            4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
            alpha
          );
        }
      }
      this._recordUnparseableColor(raw);
      return null;
    }

    const color = lower.match(/^color\(\s*([^\s]+)\s+(.+)\)$/);
    if (color) {
      const space = color[1];
      const slashParts = color[2].split('/').map(part => part.trim());
      const channelTokens = slashParts[0].split(/\s+/);
      const alpha = this._parseAlpha(slashParts[1]);
      if (channelTokens.length === 3 && alpha != null) {
        const channels = channelTokens.map(channel => this._parseUnitInterval(channel));
        if (channels.every(Number.isFinite)) {
          if (space === 'srgb') {
            return {
              r: this._clampChannel(channels[0]),
              g: this._clampChannel(channels[1]),
              b: this._clampChannel(channels[2]),
              a: alpha
            };
          }
          if (space === 'srgb-linear') {
            return this._fromLinearSrgb(channels[0], channels[1], channels[2], alpha);
          }
          if (space === 'display-p3') {
            const [pr, pg, pb] = channels.map(channel => this._srgbToLinear(channel));
            const x = 0.4865709486 * pr + 0.2656676932 * pg + 0.1982172852 * pb;
            const y = 0.2289745641 * pr + 0.6917385218 * pg + 0.0792869141 * pb;
            const z = 0.0000000000 * pr + 0.0451133820 * pg + 1.0439443689 * pb;
            return this._fromLinearSrgb(
              3.2409699419 * x - 1.5373831776 * y - 0.4986107603 * z,
              -0.9692436363 * x + 1.8759675015 * y + 0.0415550574 * z,
              0.0556300797 * x - 0.2039769589 * y + 1.0569715142 * z,
              alpha
            );
          }
        }
      }
      this._recordUnparseableColor(raw);
      return null;
    }

    // Computed styles should resolve named and HSL colors to rgb(). Any
    // remaining explicit color function is unsupported and must be visible in
    // the result instead of silently turning into a perfect score.
    if (/^(#|hsl|hwb|lab|lch|oklab|oklch|color\()/.test(lower)) {
      this._recordUnparseableColor(raw);
    }
    return null;
  },

  rgbToHex(r, g, b) {
    return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('');
  },

  rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    if (max === min) return { h: 0, s: 0, l: Math.round(l * 100) };
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h;
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
    return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) };
  },

  // Relative luminance per WCAG 2.1
  relativeLuminance(r, g, b) {
    const [rs, gs, bs] = [r, g, b].map(c => {
      c = c / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
  },

  contrastRatio(rgb1, rgb2) {
    const l1 = this.relativeLuminance(rgb1.r, rgb1.g, rgb1.b);
    const l2 = this.relativeLuminance(rgb2.r, rgb2.g, rgb2.b);
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  },

  // CIEDE2000 — perceptual color distance
  // Simplified implementation sufficient for design analysis
  rgbToLab(r, g, b) {
    // RGB -> XYZ (D65)
    let rr = r / 255, gg = g / 255, bb = b / 255;
    rr = rr > 0.04045 ? Math.pow((rr + 0.055) / 1.055, 2.4) : rr / 12.92;
    gg = gg > 0.04045 ? Math.pow((gg + 0.055) / 1.055, 2.4) : gg / 12.92;
    bb = bb > 0.04045 ? Math.pow((bb + 0.055) / 1.055, 2.4) : bb / 12.92;
    let x = (rr * 0.4124564 + gg * 0.3575761 + bb * 0.1804375) / 0.95047;
    let y = (rr * 0.2126729 + gg * 0.7151522 + bb * 0.0721750);
    let z = (rr * 0.0193339 + gg * 0.1191920 + bb * 0.9503041) / 1.08883;
    x = x > 0.008856 ? Math.pow(x, 1/3) : (7.787 * x) + 16/116;
    y = y > 0.008856 ? Math.pow(y, 1/3) : (7.787 * y) + 16/116;
    z = z > 0.008856 ? Math.pow(z, 1/3) : (7.787 * z) + 16/116;
    return { L: (116 * y) - 16, a: 500 * (x - y), b: 200 * (y - z) };
  },

  ciede2000(rgb1, rgb2) {
    const lab1 = this.rgbToLab(rgb1.r, rgb1.g, rgb1.b);
    const lab2 = this.rgbToLab(rgb2.r, rgb2.g, rgb2.b);
    // Simplified: use CIE76 as approximation (sufficient for design thresholds)
    const dL = lab1.L - lab2.L;
    const da = lab1.a - lab2.a;
    const db = lab1.b - lab2.b;
    return Math.sqrt(dL * dL + da * da + db * db);
  },

  isWarm(hue) {
    return (hue >= 0 && hue <= 60) || (hue >= 300 && hue <= 360);
  },

  isCool(hue) {
    return hue > 60 && hue < 300;
  },

  isNeutral(s) {
    return s < 10;
  },

  // HSL saturation alone overstates chroma near black and white. Multiplying
  // by the lightness envelope recovers the actual HSL chroma on a 0-100 scale.
  effectiveSaturation(hsl) {
    const lightness = Math.max(0, Math.min(100, hsl.l)) / 100;
    return hsl.s * (1 - Math.abs(2 * lightness - 1));
  },

  isStatusColor(h, s) {
    if (s < 20) return false;
    // Red zone: 340-20
    if (h >= 340 || h <= 20) return true;
    // Yellow/amber zone: 35-65
    if (h >= 35 && h <= 65) return true;
    // Green zone: 90-160
    if (h >= 90 && h <= 160) return true;
    return false;
  },

  fontWeightRange(value) {
    const normalized = String(value || 'normal').trim().toLowerCase();
    if (normalized === 'normal') return [400, 400];
    if (normalized === 'bold') return [700, 700];
    const values = (normalized.match(/\d+(?:\.\d+)?/g) || []).map(Number);
    if (values.length === 0) return [400, 400];
    return values.length === 1 ? [values[0], values[0]] : [values[0], values[1]];
  },

  // ─── DOM Traversal ───────────────────────────────────────────────

  getEffectiveBackground(el) {
    let current = el;
    while (current && current !== document.documentElement) {
      const computed = window.getComputedStyle(current);
      const backgroundImage = computed.backgroundImage;
      if (backgroundImage && backgroundImage !== 'none') {
        this._recordUnparseableColor(`background-image: ${backgroundImage}`);
        return null;
      }
      const bg = computed.backgroundColor;
      const parsed = this.parseColor(bg);
      if (parsed && parsed.a > 0.1) {
        if (parsed.a < 1 && current.parentElement) {
          // Semi-transparent — blend with parent
          const parentBg = this.getEffectiveBackground(current.parentElement);
          if (parentBg) {
            return {
              r: Math.round(parsed.r * parsed.a + parentBg.r * (1 - parsed.a)),
              g: Math.round(parsed.g * parsed.a + parentBg.g * (1 - parsed.a)),
              b: Math.round(parsed.b * parsed.a + parentBg.b * (1 - parsed.a)),
              a: 1
            };
          }
        }
        return parsed;
      }
      current = current.parentElement;
    }
    // Default: white
    return { r: 255, g: 255, b: 255, a: 1 };
  },

  isVisible(el) {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  },

  isInViewport(el) {
    const rect = el.getBoundingClientRect();
    return rect.top < window.innerHeight && rect.bottom > 0 &&
           rect.left < window.innerWidth && rect.right > 0;
  },

  documentHeight() {
    const body = document.body || {};
    const root = document.documentElement || {};
    return Math.max(
      window.innerHeight || 0,
      body.scrollHeight || 0,
      body.offsetHeight || 0,
      root.scrollHeight || 0,
      root.offsetHeight || 0,
      root.clientHeight || 0
    );
  },

  isOnPage(el) {
    const rect = el.getBoundingClientRect();
    const top = rect.top + (window.scrollY || window.pageYOffset || 0);
    const left = rect.left + (window.scrollX || window.pageXOffset || 0);
    const root = document.documentElement || {};
    const width = Math.max(window.innerWidth || 0, root.scrollWidth || 0, root.clientWidth || 0);
    return rect.width > 0 && rect.height > 0 &&
      top < this.documentHeight() && top + rect.height > 0 &&
      left < width && left + rect.width > 0;
  },

  isTextElement(el) {
    const textTags = ['P', 'SPAN', 'LI', 'TD', 'TH', 'LABEL', 'A', 'STRONG', 'EM', 'B', 'I',
                      'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'FIGCAPTION', 'CAPTION'];
    return textTags.includes(el.tagName);
  },

  isBodyText(el) {
    return ['P', 'LI', 'TD', 'TH', 'SPAN', 'LABEL'].includes(el.tagName);
  },

  isHeading(el) {
    return /^H[1-6]$/.test(el.tagName);
  },

  isInteractive(el) {
    if (['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) return true;
    if (el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link') return true;
    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;
    if (el.getAttribute('onclick') || el.getAttribute('role') === 'checkbox' ||
        el.getAttribute('role') === 'tab' || el.getAttribute('role') === 'menuitem') return true;
    return false;
  },

  isFormField(el) {
    return ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName) &&
           el.type !== 'hidden' && el.type !== 'submit' && el.type !== 'button';
  },

  getSelector(el, maxLen = 80) {
    if (el.id) return '#' + el.id;
    let sel = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\s+/).slice(0, 2).join('.');
      if (cls) sel += '.' + cls;
    }
    return sel.slice(0, maxLen);
  },

  // Collect all visible elements of specified types
  queryVisible(selector) {
    return Array.from(document.querySelectorAll(selector)).filter(el => this.isVisible(el));
  },

  // Keep bounded checks representative of the whole document. A plain
  // `slice(0, limit)` silently collapses back to the first viewport on large
  // pages because DOM order is usually top-to-bottom.
  sampleAcrossPage(elements, limit) {
    if (!Number.isFinite(limit) || limit <= 0 || elements.length <= limit) return [...elements];
    const scrollY = window.scrollY || window.pageYOffset || 0;
    const ordered = [...elements].sort((a, b) =>
      (a.getBoundingClientRect().top + scrollY) - (b.getBoundingClientRect().top + scrollY)
    );
    const sample = [];
    const denominator = Math.max(1, limit - 1);
    for (let index = 0; index < limit; index++) {
      const sourceIndex = Math.round((index / denominator) * (ordered.length - 1));
      sample.push(ordered[sourceIndex]);
    }
    return sample;
  },

  // ─── Geometry ────────────────────────────────────────────────────

  gap(rect1, rect2) {
    // Vertical gap between two rects
    if (rect1.bottom <= rect2.top) return rect2.top - rect1.bottom;
    if (rect2.bottom <= rect1.top) return rect1.top - rect2.bottom;
    return 0; // overlapping
  },

  areAdjacent(rect1, rect2, threshold = 50) {
    const dx = Math.max(0, Math.max(rect1.left - rect2.right, rect2.left - rect1.right));
    const dy = Math.max(0, Math.max(rect1.top - rect2.bottom, rect2.top - rect1.bottom));
    return Math.sqrt(dx * dx + dy * dy) < threshold;
  },

  // ─── Statistics ──────────────────────────────────────────────────

  median(arr) {
    if (!arr.length) return 0;
    const sorted = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  },

  stddev(arr) {
    if (arr.length < 2) return 0;
    const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
    return Math.sqrt(arr.reduce((sum, x) => sum + (x - mean) ** 2, 0) / arr.length);
  },

  mode(arr) {
    const counts = {};
    arr.forEach(v => { counts[v] = (counts[v] || 0) + 1; });
    let maxCount = 0, maxVal = arr[0];
    Object.entries(counts).forEach(([v, c]) => { if (c > maxCount) { maxCount = c; maxVal = v; } });
    return parseFloat(maxVal);
  },

  // Detect the base unit from a set of spacing values
  detectBaseUnit(values) {
    if (!values.length) return { unit: 8, confidence: 0 };
    const candidates = [4, 8];
    let best = { unit: 8, score: 0 };
    for (const unit of candidates) {
      const onGrid = values.filter(v => v > 0 && v % unit === 0).length;
      const score = onGrid / values.length;
      if (score > best.score) best = { unit, score };
    }
    return { unit: best.unit, confidence: Math.round(best.score * 100) / 100 };
  },

  // Detect type scale ratio from sorted font sizes
  detectScaleRatio(sizes) {
    if (sizes.length < 3) return { ratio: null, variance: 1, systematic: false };
    const ratios = [];
    for (let i = 1; i < sizes.length; i++) {
      if (sizes[i - 1] > 0) ratios.push(sizes[i] / sizes[i - 1]);
    }
    if (!ratios.length) return { ratio: null, variance: 1, systematic: false };
    const avgRatio = ratios.reduce((a, b) => a + b, 0) / ratios.length;
    const variance = this.stddev(ratios) / avgRatio;
    // Try to match known scales
    const knownScales = [1.067, 1.125, 1.200, 1.250, 1.333, 1.414, 1.500, 1.618];
    let bestMatch = avgRatio;
    let bestDist = Infinity;
    for (const s of knownScales) {
      const d = Math.abs(avgRatio - s);
      if (d < bestDist) { bestDist = d; bestMatch = s; }
    }
    return {
      ratio: Math.round(avgRatio * 1000) / 1000,
      best_known_match: bestMatch,
      variance: Math.round(variance * 1000) / 1000,
      systematic: variance < 0.15
    };
  }
};
