"""Reader and writer for Riot PROP (.bin) property files.

parse(data)               -> (linked, entries); entries = [(classHash, pathHash, fields)]
serialize(linked, entries) -> bytes (byte-identical to the input for an unmodified parse)
fields = [(nameHash, type, value)]; values: ints/floats/str, raw bytes for vectors/colors,
('list', elemType, items), ('struct', classHash, fields), ('opt', type, value|None),
('map', keyType, valueType, [(k, v)]).
"""
import struct

PRIM = {1: '<B', 2: '<b', 3: '<B', 4: '<h', 5: '<H', 6: '<i', 7: '<I', 8: '<q', 9: '<Q', 10: '<f',
        17: '<I', 18: '<Q', 132: '<I', 135: '<B'}
RAW = {11: 8, 12: 12, 13: 16, 14: 64, 15: 4}


class _R:
    def __init__(self, d):
        self.d, self.p = d, 0

    def u(self, fmt):
        v = struct.unpack_from(fmt, self.d, self.p)[0]
        self.p += struct.calcsize(fmt)
        return v

    def raw(self, n):
        b = self.d[self.p:self.p + n]
        self.p += n
        return b


def _value(r, t):
    if t in PRIM:
        return r.u(PRIM[t])
    if t in RAW:
        return r.raw(RAW[t])
    if t == 16:
        return r.raw(r.u('<H')).decode('utf-8')
    if t in (128, 129):
        et = r.u('<B')
        end = r.u('<I') + r.p
        items = [_value(r, et) for _ in range(r.u('<I'))]
        assert r.p == end, 'container size mismatch'
        return ('list', et, items)
    if t in (130, 131):
        cls = r.u('<I')
        if cls == 0:
            return ('struct', 0, [])
        end = r.u('<I') + r.p
        fields = _fields(r, r.u('<H'))
        assert r.p == end, 'struct size mismatch'
        return ('struct', cls, fields)
    if t == 133:
        et = r.u('<B')
        return ('opt', et, _value(r, et) if r.u('<B') else None)
    if t == 134:
        kt, vt = r.u('<B'), r.u('<B')
        end = r.u('<I') + r.p
        pairs = [(_value(r, kt), _value(r, vt)) for _ in range(r.u('<I'))]
        assert r.p == end, 'map size mismatch'
        return ('map', kt, vt, pairs)
    raise ValueError('unknown property type %d' % t)


def _fields(r, n):
    out = []
    for _ in range(n):
        nh, t = r.u('<I'), r.u('<B')
        out.append((nh, t, _value(r, t)))
    return out


def parse(d):
    r = _R(d)
    assert r.raw(4) == b'PROP', 'not a PROP file'
    ver = r.u('<I')
    linked = []
    if ver >= 2:
        linked = [r.raw(r.u('<H')).decode() for _ in range(r.u('<I'))]
    classes = [r.u('<I') for _ in range(r.u('<I'))]
    entries = []
    for cls in classes:
        end = r.u('<I') + r.p
        ph = r.u('<I')
        entries.append((cls, ph, _fields(r, r.u('<H'))))
        assert r.p == end, 'entry length mismatch'
    assert r.p == len(d), 'trailing bytes'
    return ver, linked, entries


def _w_value(t, v):
    if t in PRIM:
        return struct.pack(PRIM[t], v)
    if t in RAW:
        return v
    if t == 16:
        b = v.encode('utf-8')
        return struct.pack('<H', len(b)) + b
    if t in (128, 129):
        body = b''.join(_w_value(v[1], x) for x in v[2])
        return struct.pack('<BII', v[1], 4 + len(body), len(v[2])) + body
    if t in (130, 131):
        if v[1] == 0:
            return struct.pack('<I', 0)
        body = _w_fields(v[2])
        return struct.pack('<IIH', v[1], 2 + len(body), len(v[2])) + body
    if t == 133:
        if v[2] is None:
            return struct.pack('<BB', v[1], 0)
        return struct.pack('<BB', v[1], 1) + _w_value(v[1], v[2])
    if t == 134:
        body = b''.join(_w_value(v[1], k) + _w_value(v[2], x) for k, x in v[3])
        return struct.pack('<BBII', v[1], v[2], 4 + len(body), len(v[3])) + body
    raise ValueError('unknown property type %d' % t)


def _w_fields(fields):
    return b''.join(struct.pack('<IB', nh, t) + _w_value(t, v) for nh, t, v in fields)


def serialize(ver, linked, entries):
    out = [b'PROP', struct.pack('<I', ver)]
    if ver >= 2:
        out.append(struct.pack('<I', len(linked)))
        for s in linked:
            b = s.encode()
            out.append(struct.pack('<H', len(b)) + b)
    out.append(struct.pack('<I', len(entries)))
    out.extend(struct.pack('<I', e[0]) for e in entries)
    for cls, ph, fields in entries:
        body = _w_fields(fields)
        out.append(struct.pack('<IIH', 4 + 2 + len(body), ph, len(fields)) + body)
    return b''.join(out)
