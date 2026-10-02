"""Read HotSpot HPROF and count byte-array storage reachable from Parquet slabs.

This is a targeted buffer inspection, not a dominator/retained-size analysis.
"""
import collections
import json
import mmap
import struct
import sys

f = open(sys.argv[1], 'rb')
m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
p = m.find(b'\0') + 1
ids = struct.unpack_from('>I', m, p)[0]
p += 12
sizes = {2: ids, 4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
def num(pos, n): return int.from_bytes(m[pos:pos+n], 'big')
strings, names, classes, objects, arrays, prims = {}, {}, {}, {}, {}, {}
root_sizes = {0xff: ids, 1: ids*2, 2: ids+8, 3: ids+8, 4: ids+4,
              5: ids, 6: ids+4, 7: ids, 8: ids+8, 0x89: ids, 0x8a: ids,
              0x8b: ids, 0x8c: ids, 0x8d: ids+8, 0x8e: ids, 0x90: ids}
while p < len(m):
    tag = m[p]; length = num(p+5, 4); q = p+9; end = q+length
    if tag == 1:
        strings[num(q, ids)] = m[q+ids:end].decode('utf8', errors='replace')
    elif tag == 2:
        names[num(q+4, ids)] = num(q+8+ids, ids)
    elif tag in (0x0c, 0x1c):
        while q < end:
            t = m[q]; q += 1
            if t in root_sizes: q += root_sizes[t]
            elif t == 0x20:
                oid = num(q, ids); q += ids+4
                sup = num(q, ids); q += ids*6
                instance_size = num(q, 4); q += 4
                n = num(q, 2); q += 2
                for _ in range(n):
                    typ = m[q+2]; q += 3+sizes[typ]
                n = num(q, 2); q += 2
                for _ in range(n):
                    typ = m[q+ids]; q += ids+1+sizes[typ]
                n = num(q, 2); q += 2
                fields = []
                for _ in range(n):
                    fields.append((num(q, ids), m[q+ids])); q += ids+1
                classes[oid] = (sup, fields, instance_size)
            elif t == 0x21:
                oid = num(q, ids); cls = num(q+ids+4, ids)
                n = num(q+ids*2+4, 4); q += ids*2+8
                objects[oid] = (cls, q, n); q += n
            elif t == 0x22:
                oid = num(q, ids); n = num(q+ids+4, 4)
                q += ids*2+8; arrays[oid] = (q, n); q += n*ids
            elif t == 0x23:
                oid = num(q, ids); n = num(q+ids+4, 4); typ = m[q+ids+8]
                q += ids+9; prims[oid] = (typ, n); q += n*sizes[typ]
            elif t == 0xfe: q += 4+ids
            else: raise ValueError(f'Unknown heap tag {t:x} at {q-1}')
    p = end

def cname(cls): return strings.get(names.get(cls), '')
def fields(oid):
    cls, q, length = objects[oid]
    result = {}
    start = q
    while cls:
        sup, fs, _ = classes[cls]
        for name, typ in fs:
            result[strings[name]] = (typ, num(q, sizes[typ])); q += sizes[typ]
        cls = sup
    assert q-start == length, (oid, q-start, length)
    return result

counts = collections.Counter(cname(c) for c, _, _ in objects.values())
slabs = [o for o, (c, _, _) in objects.items() if cname(c).endswith('/CapacityByteArrayOutputStream')]
seen, pending, byte_arrays = set(), list(slabs), set()
allowed = ('java/util/ArrayList', 'java/nio/HeapByteBuffer', 'java/nio/ByteBuffer',
           'java/nio/HeapByteBufferR')
while pending:
    oid = pending.pop()
    if not oid or oid in seen: continue
    seen.add(oid)
    if oid in prims:
        if prims[oid][0] == 8: byte_arrays.add(oid)
    elif oid in arrays:
        q, n = arrays[oid]
        pending.extend(num(q+i*ids, ids) for i in range(n))
    elif oid in objects:
        name = cname(objects[oid][0])
        if name in allowed or name.endswith('/CapacityByteArrayOutputStream'):
            pending.extend(value for typ, value in fields(oid).values() if typ == 2)

strategies = []
for oid, (cls, _, _) in objects.items():
    if cname(cls).endswith('/ParquetWriteStrategy'):
        fs = fields(oid)
        map_id = fs['beingWrittenWriter'][1]
        strategies.append({'writer_map_size': fields(map_id)['size'][1],
                           'currentBatchSize': fs.get('currentBatchSize', (0, None))[1]})
writer_roots = [o for o,(c,_,_) in objects.items() if cname(c).endswith('/ParquetWriter')]
writer_seen, writer_pending, writer_bytes = set(), list(writer_roots), set()
writer_types = collections.Counter()
while writer_pending:
    oid = writer_pending.pop()
    if not oid or oid in writer_seen: continue
    writer_seen.add(oid)
    if oid in prims:
        if prims[oid][0] == 8: writer_bytes.add(oid)
    elif oid in arrays:
        q, n = arrays[oid]
        writer_pending.extend(num(q+i*ids, ids) for i in range(n))
    elif oid in objects:
        name = cname(objects[oid][0])
        if ('/org/apache/parquet/' in name or '/org/apache/hadoop/io/compress/' in name
            or name.startswith(('java/util/', 'java/nio/'))
            or name == 'java/io/ByteArrayOutputStream'):
            writer_types[name] += 1
            writer_pending.extend(v for t,v in fields(oid).values() if t == 2)
result = {
    'file': sys.argv[1], 'object_count': len(objects),
    'parquet_writer_count': sum(v for k,v in counts.items() if k.endswith('/ParquetWriter')),
    'strategies': strategies, 'capacity_stream_count': len(slabs),
    'unique_slab_byte_arrays': len(byte_arrays),
    'slab_byte_array_payload_bytes': sum(prims[o][1] for o in byte_arrays),
    'all_byte_array_payload_bytes': sum(n for typ,n in prims.values() if typ == 8),
    'writer_reachable_byte_array_payload_bytes': sum(prims[o][1] for o in writer_bytes),
    'writer_reachable_byte_arrays': len(writer_bytes),
    'writer_reachable_classes': dict(writer_types.most_common(25)),
    'note': 'Unique reachable byte[] payload via specified buffer/container classes; excludes object overhead; not a dominator or retained-size analysis.'
}
print(json.dumps(result, indent=2))
