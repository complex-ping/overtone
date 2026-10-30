/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Overtone builder: runs patcher/patch.py (Python, in Pyodide) off the page's thread. Python checks and unpacks the stock
 * file and seals the result; the packing between those two steps runs in pack-worker.js (the same packer in JavaScript).
 * In:  {cmd: "boot", pack}  -> {booted: true} (loads Python ahead of the build)
 *      {cmd: "prepare", pack, input: {name, bytes}}  -> {jobs: {3: bytes, 7: bytes}, depth}
 *      {cmd: "finish", streams: {3: bytes, 7: bytes}}  -> {done: bytes} (after "prepare" ran in this worker)
 * Out on any failure: {error: text, refused: bool} (refused = the patcher said no, with a message for the user). */
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
importScripts(PYODIDE + "pyodide.js");

// The patcher's Python files, as in the repository (patcher/).
const FILES = [
  "patch.py",
  "_dnfw/__init__.py",
  "_dnfw/codec/__init__.py", "_dnfw/codec/aplib.py", "_dnfw/codec/aplibpack.py", "_dnfw/codec/limits.py",
  "_dnfw/container/__init__.py", "_dnfw/container/ele3.py", "_dnfw/container/section.py",
  "_dnfw/firmware/__init__.py", "_dnfw/firmware/build.py", "_dnfw/firmware/load.py", "_dnfw/firmware/model.py",
  "_dnfw/integrity/__init__.py", "_dnfw/integrity/checksum.py", "_dnfw/integrity/digest.py",
  "_dnfw/integrity/keyderive.py",
  "_dnfw/syx/__init__.py", "_dnfw/syx/checksum.py", "_dnfw/syx/encode87.py", "_dnfw/syx/frame.py",
  "_dnfw/syx/transport.py",
];
const ROOT = "/overtone/patcher";

let py = null, booting = null;

// once per worker: "boot" (sent when a file is dropped) and "prepare" can both be waiting on it
function boot(pack) { return booting || (booting = load(pack)); }
async function load(pack) {
  py = await loadPyodide({ indexURL: PYODIDE });
  const base = new URL("../patcher/", self.location.href);
  // four at a time: a small server (python3 -m http.server queues 5 connections) refuses two dozen at once
  const todo = [...FILES, "packs/" + pack + ".json"], got = [];
  await Promise.all([0, 1, 2, 3].map(async () => {
    for (let f; (f = todo.shift()) !== undefined;) {
      const r = await fetch(new URL(f, base), { cache: "no-cache" });
      if (!r.ok) throw new Error("could not fetch patcher/" + f + " (" + r.status + ")");
      got.push([f, new Uint8Array(await r.arrayBuffer())]);
    }
  }));
  for (const [f, bytes] of got) {
    py.FS.mkdirTree((ROOT + "/" + f).replace(/\/[^/]*$/, ""));
    py.FS.writeFile(ROOT + "/" + f, bytes);
  }
  py.runPython(`
import sys
sys.path.insert(0, "${ROOT}")
import patch
`);
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.cmd === "boot") {
      await boot(m.pack);
      self.postMessage({ booted: true });
    } else if (m.cmd === "prepare") {
      await boot(m.pack);
      self.postMessage({ phase: "unpack" });
      const name = /\.zip$/i.test(m.input.name) ? "/in/input.zip" : "/in/input.syx";
      py.FS.mkdirTree("/in");
      py.FS.writeFile(name, m.input.bytes);
      py.globals.set("PACK", m.pack);
      py.globals.set("INPUT", name);
      py.runPython(`
import pathlib
from pyodide.ffi import to_js
PK = patch.packs()[PACK]
raw, _ = patch.read_input(pathlib.Path(INPUT))
FW, JOBS = patch.prepare(PK, raw)
J3, J7 = (to_js(next(j[2] for j in JOBS if j[0] == sid)) for sid in (3, 7))
DEPTH = PK['chain_depth']
`);
      const jobs = { 3: py.globals.get("J3").slice(), 7: py.globals.get("J7").slice() };
      self.postMessage({ jobs, depth: py.globals.get("DEPTH") }, [jobs[3].buffer, jobs[7].buffer]);
    } else if (m.cmd === "finish") {
      py.globals.set("S3", m.streams[3]);
      py.globals.set("S7", m.streams[7]);
      py.runPython(`
from pyodide.ffi import to_js
from _dnfw.codec import aplibpack
streams = {3: bytes(S3.to_py()), 7: bytes(S7.to_py())}
# patch._compress as the command line runs it, with the stream the JavaScript packer made for each section in place of
# aplibpack.pack's: dnfw still writes the section header and padding
plain = aplibpack.pack
try:
    z = {}
    for job in JOBS:
        aplibpack.pack = lambda d, chain_depth, s=streams[job[0]]: s
        z[job[0]] = patch._compress(job)
finally:
    aplibpack.pack = plain
OUT = to_js(patch.finish(PK, FW, z))
`);
      const done = py.globals.get("OUT").slice();
      self.postMessage({ done }, [done.buffer]);
    }
  } catch (err) {
    let msg = String((err && err.message) || err);
    const refused = msg.match(/Refused: (.*)/);
    if (refused) msg = refused[1];
    else if (msg.includes("Traceback")) {
      // the exception's own line, not the hints Pyodide adds after it
      const lines = msg.trim().split("\n");
      msg = lines.filter(l => /^[\w.]+(Error|Exception)\b/.test(l)).pop() || lines.pop();
    }
    self.postMessage({ error: msg, refused: !!refused });
  }
};
