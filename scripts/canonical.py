"""Project keccak256-jcs: strict JSON, sorted Python keys, compact UTF-8.

This deliberately implements the project's named serialization contract, not
general RFC 8785 number formatting. Floats are never accepted.
"""
import json
from pathlib import Path

MASK = (1 << 64) - 1
RC = (0x1, 0x8082, 0x800000000000808A, 0x8000000080008000,
      0x808B, 0x80000001, 0x8000000080008081, 0x8000000000008009,
      0x8A, 0x88, 0x80008009, 0x8000000A, 0x8000808B,
      0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
      0x8000000000008002, 0x8000000000000080, 0x800A,
      0x800000008000000A, 0x8000000080008081, 0x8000000000008080,
      0x80000001, 0x8000000080008008)
ROT = (0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39,
       41, 45, 15, 21, 8, 18, 2, 61, 56, 14)


def _rol(v, n):
    return ((v << n) | (v >> (64 - n))) & MASK


def _permute(a):
    for rc in RC:
        c = [a[x] ^ a[x+5] ^ a[x+10] ^ a[x+15] ^ a[x+20] for x in range(5)]
        d = [c[(x-1) % 5] ^ _rol(c[(x+1) % 5], 1) for x in range(5)]
        b = [0] * 25
        for y in range(5):
            for x in range(5):
                b[y + 5*((2*x+3*y) % 5)] = _rol(a[x+5*y] ^ d[x], ROT[x+5*y])
        for y in range(5):
            for x in range(5):
                a[x+5*y] = b[x+5*y] ^ ((~b[(x+1) % 5+5*y]) & b[(x+2) % 5+5*y])
        a[0] ^= rc


def keccak256(data):
    if not isinstance(data, bytes):
        raise TypeError('keccak256 requires bytes')
    # Keccak domain 0x01, not SHA3 domain 0x06.
    padded = bytearray(data)
    padded.append(1)
    padded.extend(b'\0' * ((-len(padded)) % 136))
    padded[-1] |= 0x80
    state = [0] * 25
    for offset in range(0, len(padded), 136):
        for lane in range(17):
            start = offset + lane*8
            state[lane] ^= int.from_bytes(padded[start:start+8], 'little')
        _permute(state)
    return '0x' + b''.join(v.to_bytes(8, 'little') for v in state)[:32].hex()


def validate(value):
    if value is None or type(value) in (str, bool):
        return
    if type(value) is int:
        if abs(value) > 2**53:
            raise ValueError('integer beyond 2^53 must be a string')
    elif type(value) is list:
        for item in value:
            validate(item)
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError('non-string key')
            validate(item)
    else:
        raise ValueError('floats and non-JSON types are forbidden')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _reject_number(value):
    raise ValueError('floating point / non-finite JSON number forbidden')


def loads(text):
    value = json.loads(text, object_pairs_hook=_pairs, parse_float=_reject_number,
                       parse_constant=_reject_number)
    validate(value)
    return value


def load(path):
    return loads(Path(path).read_text(encoding='utf-8'))


def canonical_bytes(value):
    validate(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def canonical_hash(value):
    return keccak256(canonical_bytes(value))
