#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make an Overtone build for the Digitone II from Elektron's own OS 1.12 file.

    python3 patch.py Digitone_II_OS1.12_dist.zip          (or the unzipped folder, or the .syx)
    python3 patch.py --list
    python3 patch.py --pack Overtone-1.0 Digitone_II_OS1.12.syx

Needs Python 3.11 or later and nothing else. It:
  1. checks that the input is Elektron's original Digitone II OS 1.12 (sha256 7e5b8a73...ceb35);
  2. unpacks its MAIN OS (section 3) and DSP program (section 7);
  3. rebuilds the pack's versions of both: copies from your file plus our bytes;
  4. packs them again, seals the file with the key your file's bootstrap holds, and
  5. saves the result next to the input only if its sha256 is the tested build's.

The packs hold no Elektron bytes (no 16-byte run of them is in Elektron's file). The firmware container code in _dnfw/
is from dnfw (angellinares/dn2_firmware_explore, AGPL-3.0-or-later)."""
import argparse
import base64
import hashlib
import json
import pathlib
import sys
import time
import zipfile
import zlib
from concurrent.futures import ProcessPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STOCK_SHA = '7e5b8a733d4ab1fdf7e5d22757f7d8eddaa3cbf71d0858874a791844c02ceb35'
STOCK_NAME = 'Digitone_II_OS1.12.syx'


class Refused(Exception):
    pass


def packs():
    out = {}
    for p in sorted((HERE / 'packs').glob('*.json')):
        d = json.loads(p.read_text())
        out[d['id']] = d
    return out


def read_input(path):
    """The stock .syx from a .zip, a folder or the file itself."""
    if not path.exists():
        raise Refused(f'{path}: no such file or folder.')
    if path.is_dir():
        found = sorted(path.rglob('*.syx'))
        found = [f for f in found if f.name == STOCK_NAME] or found
        if len(found) != 1:
            raise Refused(f'{path}: expected {STOCK_NAME} in this folder, found {len(found)} .syx files.')
        return found[0].read_bytes(), found[0].parent
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith('.syx') and not n.startswith('__MACOSX')]
            if len(names) != 1:
                raise Refused(f'{path}: expected one .syx inside, found {len(names)}.')
            return z.read(names[0]), path.parent
    return path.read_bytes(), path.parent


def _compress(job):
    sid, dest, data, depth = job
    from _dnfw.codec import aplibpack
    from _dnfw.container import section
    plain = aplibpack.pack
    aplibpack.pack = lambda d: plain(d, chain_depth=depth)
    return section.compress(sid, dest, data)


def make(pack, raw, log=print):
    from _dnfw.firmware.load import load
    from _dnfw.firmware import build
    if hashlib.sha256(raw).hexdigest() != pack['stock_sha256']:
        if hashlib.sha256(raw).hexdigest() == pack['out_sha256']:
            raise Refused('This file is already this build. Give Elektron\'s original OS 1.12 file.')
        raise Refused('This is not Elektron\'s original Digitone II OS 1.12 file '
                      f'(sha256 must be {pack["stock_sha256"]}).')
    fw = load(raw)
    secs = {s.id: s for s in fw.container.sections}
    pool = {3: bytes(secs[3].unpack()), 7: bytes(secs[7].unpack())}
    lit = zlib.decompress(base64.b64decode(pack['lit']))
    jobs = []
    for sid in (3, 7):
        out = bytearray()
        for s, o, n in pack['sections'][str(sid)]:
            out += (lit if s == -1 else pool[s])[o:o + n]
        jobs.append((sid, secs[sid].dest, bytes(out), pack['chain_depth']))
    log('Packing the MAIN OS and the DSP program (1 to 3 minutes)...')
    t = time.time()
    with ProcessPoolExecutor(2) as ex:
        z = dict(zip((3, 7), ex.map(_compress, jobs)))
    log(f'  done in {time.time() - t:.0f} s')
    out = build.build(fw, z)
    got = hashlib.sha256(out).hexdigest()
    if got != pack['out_sha256']:
        raise Refused(f'The result is not the tested build (sha256 {got}, expected {pack["out_sha256"]}). '
                      'Nothing was saved. Please report this.')
    return out


def main():
    ap = argparse.ArgumentParser(description='Make an Overtone build for the Digitone II from Elektron\'s OS 1.12 file.')
    ap.add_argument('input', nargs='?', help='Digitone_II_OS1.12_dist.zip, its folder, or Digitone_II_OS1.12.syx')
    ap.add_argument('--pack', help='the build to make (see --list)')
    ap.add_argument('--list', action='store_true', help='list the builds this patcher can make')
    ap.add_argument('-o', '--out', help='where to save the build (default: next to the input)')
    a = ap.parse_args()
    if sys.version_info < (3, 11):
        sys.exit('Needs Python 3.11 or later.')
    ps = packs()
    if a.list or not a.input:
        for p in ps.values():
            print(f'{p["id"]}: {p["title"]}')
        if not a.input and not a.list:
            ap.print_usage()
        return
    if a.pack:
        if a.pack not in ps:
            sys.exit(f'No pack {a.pack!r}. Packs: {", ".join(ps)}')
        pack = ps[a.pack]
    elif len(ps) == 1:
        pack = next(iter(ps.values()))
    else:
        sys.exit(f'Choose a build with --pack: {", ".join(ps)}')
    try:
        raw, where = read_input(pathlib.Path(a.input.strip().strip('\'"')).expanduser())
        dst = pathlib.Path(a.out) if a.out else where / pack['out_name']
        if dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest() != pack['out_sha256']:
            raise Refused(f'{dst} exists and is not this build. Move it away first.')
        print(f'Making {pack["id"]} ({pack["title"]}) from {a.input}')
        out = make(pack, raw)
    except Refused as e:
        sys.exit(f'Refused: {e}')
    dst.write_bytes(out)
    print(f'Saved {dst}\n  sha256 {pack["out_sha256"]}\n'
          'Send it to the Digitone with Elektron Transfer (keep the volume down the first time it plays).')


if __name__ == '__main__':
    main()
