/* SPDX-License-Identifier: AGPL-3.0-or-later
 * The aPLib packer of patcher/_dnfw/codec/aplibpack.py, line for line in JavaScript: the web builder's Python (Pyodide)
 * packs ten times slower than this. Same greedy parse with one-position lazy lookahead, same cost model, same 2-byte hash
 * chains, same window and match cap, so the stream is byte for byte the Python one; the page checks the finished file's
 * sha256 against the tested build all the same.
 * In:  {data: Uint8Array, depth}  ->  {progress: 0..1} ... then {stream: Uint8Array} */

const OFFSET_BIAS = 767, REUSE_GAMMA = 2, FAR_THRESHOLD = 3328, MIN_MATCH = 2;   // codec/aplib.py
const MAX_MATCH = 2048, PACK_MAX_OFFSET = (1 << 20) - 4096;                       // codec/limits.py
const LITERAL_BITS = 9;

const bitLength = (v) => 32 - Math.clz32(v);
const gammaCost = (v) => 2 * (bitLength(v) - 1);
function matchCost(offset, length, lastOffset) {
  let bits = 1 + (offset === lastOffset ? 2 : gammaCost((offset + OFFSET_BIAS) >> 8) + 8);
  const base = length - 1 - (offset > FAR_THRESHOLD ? 1 : 0);
  bits += base <= 3 ? 2 : 2 + gammaCost(base - 2);
  return bits;
}
const minMatch = (offset) => (offset > FAR_THRESHOLD ? MIN_MATCH + 1 : MIN_MATCH);

class Writer {
  constructor(size) { this.out = new Uint8Array(size + (size >> 3) + 64); this.n = 0; this.tagPos = -1; this.tagBits = 0; }
  push(v) {
    if (this.n === this.out.length) { const o = new Uint8Array(this.out.length * 2); o.set(this.out); this.out = o; }
    this.out[this.n++] = v;
  }
  bit(v) {
    if (this.tagBits === 0) { this.tagPos = this.n; this.push(0); this.tagBits = 8; }
    if (v) this.out[this.tagPos] |= 1 << (this.tagBits - 1);
    this.tagBits--;
  }
  gamma(v) {
    for (let i = bitLength(v) - 2; i >= 0; i--) { this.bit((v >> i) & 1); this.bit(i === 0 ? 1 : 0); }
  }
  literal(v) { this.bit(1); this.push(v); }
  match(offset, length, lastOffset) {
    this.bit(0);
    if (offset === lastOffset) this.gamma(REUSE_GAMMA);
    else { const raw = offset + OFFSET_BIAS; this.gamma(raw >> 8); this.push(raw & 0xff); lastOffset = offset; }
    const base = length - 1 - (offset > FAR_THRESHOLD ? 1 : 0);
    if (base <= 3) { this.bit(base >> 1); this.bit(base & 1); }
    else { this.bit(0); this.bit(0); this.gamma(base - 2); }
    return lastOffset;
  }
  end() { this.bit(0); this.gamma(0x1000002); this.push(0xff); }
}

function run(d, a, b, cap) {
  let n = 0;
  while (n < cap && d[a + n] === d[b + n]) n++;
  return n;
}

// Best [offset, length, cost] at i, longest first, ties to the lower cost, then to the first found (aplibpack._best).
function best(d, i, cap, head, prev, lastOffset, depth, maxOffset, r) {
  let bo = 0, bl = 0, bc = 0;
  const consider = (offset, length) => {
    if (length < minMatch(offset)) return;
    const cost = matchCost(offset, length, lastOffset);
    if (length > bl || (length === bl && cost < bc)) { bo = offset; bl = length; bc = cost; }
  };
  if (lastOffset > 0 && lastOffset <= Math.min(i, maxOffset)) consider(lastOffset, run(d, i - lastOffset, i, cap));
  if (i + 2 <= d.length) {
    let c = head[(d[i] << 8) | d[i + 1]];
    while (c >= 0 && depth) {
      if (i - c > maxOffset) break;
      consider(i - c, run(d, c, i, cap));
      if (bl >= cap) break;
      c = prev[c];
      depth--;
    }
  }
  r[0] = bo; r[1] = bl; r[2] = bc;
}

function pack(d, depth, progress) {
  const size = d.length, w = new Writer(size);
  if (size === 0) { w.end(); return w.out.slice(0, w.n); }
  const head = new Int32Array(65536).fill(-1), prev = new Int32Array(size).fill(-1);
  const r = [0, 0, 0], alt = [0, 0, 0], step1 = Math.max(1, Math.floor(size / 100));
  let lastOffset = 1, i = 0, nextReport = 0;
  while (i < size) {
    if (progress && i >= nextReport) { progress(i / size); nextReport = i + step1; }
    const cap = Math.min(size - i, MAX_MATCH);
    best(d, i, cap, head, prev, lastOffset, depth, PACK_MAX_OFFSET, r);
    let [offset, length, cost] = r;
    if (length && i + 1 < size) {
      best(d, i + 1, Math.min(size - i - 1, MAX_MATCH), head, prev, lastOffset, depth, PACK_MAX_OFFSET, alt);
      if (alt[1] && (LITERAL_BITS + alt[2]) * length < cost * (1 + alt[1])) length = 0;
    }
    let step;
    if (length) { lastOffset = w.match(offset, length, lastOffset); step = length; }
    else { w.literal(d[i]); step = 1; }
    const limit = Math.min(i + step, size - 2 + 1);
    for (let k = i; k < limit; k++) {
      const key = (d[k] << 8) | d[k + 1];
      prev[k] = head[key];
      head[key] = k;
    }
    i += step;
  }
  w.end();
  return w.out.slice(0, w.n);
}

if (typeof WorkerGlobalScope !== "undefined" && self instanceof WorkerGlobalScope) {
  self.onmessage = (e) => {
    const stream = pack(e.data.data, e.data.depth, (f) => self.postMessage({ progress: f }));
    self.postMessage({ progress: 1 });
    self.postMessage({ stream }, [stream.buffer]);
  };
}
