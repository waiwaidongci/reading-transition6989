"""编辑演练的分批受理与合齐。

受理时每批写一个紧凑二进制分块（章节名长度 + 计数），磁盘增量写入；求解前
按批次流式读回、去重合并。这样“五万种接续分批读入、合齐后统一求解”不会把
原始批次同时留在内存里，受理与求解各自的内存峰值可独立测量。
"""
import hashlib
import struct
import threading
from pathlib import Path

MAX_BATCH = 5000
MAX_CONTINUATIONS = 50000
MEMORY_BUDGET_MB = 192


def memory_mb(base=0):
    """当前进程常驻内存（MB）；读取失败时返回基准值。"""
    try:
        with open('/proc/self/status', encoding='ascii') as handle:
            for line in handle:
                if line.startswith('VmRSS:'):
                    return max(base, int(line.split()[1]) / 1024)
    except OSError:
        pass
    return base


def _chunk_dir(root, trail_id):
    path = Path(root) / 'drills' / str(trail_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_batch(root, trail_id, batch_index, rows):
    """写一批规范化接续，返回回执（路径、条数、SHA256、字节数）。"""
    digest = hashlib.sha256()
    buffer = bytearray()
    for row in rows:
        source = row['from'].encode('utf-8')
        target = row['to'].encode('utf-8')
        header = struct.pack('>HHQ', len(source), len(target), row['count'])
        digest.update(header)
        digest.update(source)
        digest.update(target)
        buffer += header
        buffer += source
        buffer += target
    path = _chunk_dir(root, trail_id) / f'batch-{batch_index:05d}.bin'
    path.write_bytes(buffer)
    return {'path': str(path), 'count': len(rows), 'sha256': digest.hexdigest(), 'bytes': len(buffer)}


def merge_batches(root, trail_id, indexes):
    """按批次顺序流式读回并合齐成去重后的接续目录（排序后的 list）。"""
    directory = _chunk_dir(root, trail_id)
    merged = {}
    for index in indexes:
        data = (directory / f'batch-{index:05d}.bin').read_bytes()
        position = 0
        size = len(data)
        while position < size:
            source_length, target_length, count = struct.unpack_from('>HHQ', data, position)
            position += 12
            source = data[position:position + source_length].decode('utf-8')
            position += source_length
            target = data[position:position + target_length].decode('utf-8')
            position += target_length
            key = (source, target)
            current = merged.get(key)
            if current is None:
                if len(merged) >= MAX_CONTINUATIONS:
                    raise ValueError('接续种类超过 50000，请分批提交')
                merged[key] = count
            else:
                merged[key] = current + count
    return [{'from': key[0], 'to': key[1], 'count': merged[key]} for key in sorted(merged)]


def delete_chunks(root, trail_id):
    for path in _chunk_dir(root, trail_id).glob('batch-*.bin'):
        try:
            path.unlink()
        except OSError:
            pass
