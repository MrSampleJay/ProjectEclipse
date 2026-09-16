"""Create a verified, analysis-only ARM64 ELF from the extracted Switch NSO.

Only Python's standard library is required. Original research inputs are never
modified. Segment hashes are checked before applying relative relocations to the
derived image. The ELF is an IDA analysis container, not a runnable game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "ResearchSources/reversingsf2/decompilation"
BUILD = RESEARCH / "reference_builds/switch_v1.1.0/program"
DUMP = RESEARCH / "generated/switch_il2cpp/il2cppdumper"

TARGETS = [
    0xD94FD0,  # PvpScene.HaveSecondPlayer
    0xEB6EF0,  # PvpRule.CompareSingle
    0xC92600,  # InputData.IsInputEqual
    0xD97430,  # PvpScene.SwitchInputToNextDevice
    0xD97260,  # PvpScene.SwitchToNextNotOwnedDevice
    0xD96FB0,  # PvpScene.GetModelParameters
    0xD44F00,  # GameUtils.CreateFightPVP
    0xC927A0,  # InputSelector.SetModelInput
    0xC92B60,  # InputSelector.GetModelTeam
    0xC92950,  # InputSelector.GetModel
    0xD96C50,  # PvpScene.GetLocationNode
    0xD961F0,  # PvpScene.StartFight
    0xE51A20,  # EndPvpFightScreen.ReplayHandler
    0xE51760,  # EndPvpFightScreen.CloseHandler
]


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def lz4_block(source: bytes, expected: int) -> bytearray:
    """Decode an NSO raw LZ4 block, including overlapping match copies."""
    result = bytearray()
    cursor = 0

    def length(value: int) -> int:
        nonlocal cursor
        if value == 15:
            while True:
                if cursor >= len(source):
                    raise ValueError("Truncated LZ4 length")
                extra = source[cursor]
                cursor += 1
                value += extra
                if extra != 255:
                    break
        return value

    while cursor < len(source):
        token = source[cursor]
        cursor += 1
        literals = length(token >> 4)
        if cursor + literals > len(source) or len(result) + literals > expected:
            raise ValueError("Invalid LZ4 literal length")
        result.extend(source[cursor:cursor + literals])
        cursor += literals
        if cursor == len(source):
            break
        if cursor + 2 > len(source):
            raise ValueError("Truncated LZ4 match offset")
        offset = struct.unpack_from("<H", source, cursor)[0]
        cursor += 2
        match = length(token & 15) + 4
        if offset == 0 or offset > len(result) or len(result) + match > expected:
            raise ValueError("Invalid LZ4 match")
        chunk = bytes(result[-offset:])
        result.extend((chunk * ((match + offset - 1) // offset))[:match])
    if len(result) != expected:
        raise ValueError(f"Wrong LZ4 size: {len(result)} != {expected}")
    return result


def align(value: int, boundary: int = 0x1000) -> int:
    return (value + boundary - 1) & -boundary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New output directory, normally under Temp")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Use a new directory to preserve earlier evidence: {output}")

    original = (BUILD / "exefs/main").read_bytes()
    if original[:4] != b"NSO0":
        raise ValueError("Expected NSO0 input")
    flags = struct.unpack_from("<I", original, 0xC)[0]
    compressed = struct.unpack_from("<III", original, 0x60)
    segments = []
    for index, name in enumerate((".text", ".rodata", ".data")):
        file_offset, address, size = struct.unpack_from("<III", original, 0x10 + index * 16)
        stored_size = compressed[index] if flags & (1 << index) else size
        if file_offset + stored_size > len(original):
            raise ValueError(f"Segment {name} exceeds the file")
        stored = original[file_offset:file_offset + stored_size]
        contents = lz4_block(stored, size) if flags & (1 << index) else bytearray(stored)
        actual = digest(contents)
        expected = original[0xA0 + index * 32:0xC0 + index * 32].hex()
        if not flags & (1 << (index + 3)) or actual != expected:
            raise ValueError(f"Missing or mismatched NSO segment hash for {name}")
        segments.append({"name": name, "address": address, "size": size,
                         "sha256": actual, "contents": contents})
        print(f"VERIFIED {name}: RVA 0x{address:X}, {size} bytes, SHA-256 {actual}", flush=True)

    def locate(address: int, length: int = 8):
        for segment in segments:
            relative = address - segment["address"]
            if 0 <= relative and relative + length <= segment["size"]:
                return segment["contents"], relative
        raise ValueError(f"RVA outside file-backed segments: 0x{address:X}")

    def unpack(fmt: str, address: int):
        data, offset = locate(address, struct.calcsize(fmt))
        return struct.unpack_from(fmt, data, offset)

    mod_offset = unpack("<I", 4)[0]
    if bytes(segments[0]["contents"][mod_offset:mod_offset + 4]) != b"MOD0":
        raise ValueError("NSO MOD0 header not found")
    dynamic_rva = mod_offset + unpack("<I", mod_offset + 4)[0]
    dynamic = {}
    for index in range(4096):
        tag, value = unpack("<QQ", dynamic_rva + index * 16)
        if tag == 0:
            break
        dynamic[tag] = value
    else:
        raise ValueError("Unterminated dynamic table")

    relocations = Counter()
    unresolved = []
    resolved_symbol_relocations = 0
    for pointer_tag, size_tag in ((7, 8), (23, 2)):
        if pointer_tag not in dynamic:
            continue
        if dynamic.get(9, 24) != 24 or dynamic[size_tag] % 24:
            raise ValueError("Unsupported relocation entry size")
        for index in range(dynamic[size_tag] // 24):
            target, info, addend = unpack("<QQq", dynamic[pointer_tag] + index * 24)
            kind, symbol = info & 0xFFFFFFFF, info >> 32
            relocations[kind] += 1
            if kind == 1027:  # R_AARCH64_RELATIVE, image base is zero.
                data, offset = locate(target)
                struct.pack_into("<Q", data, offset, addend & 0xFFFFFFFFFFFFFFFF)
            elif kind in (257, 1025, 1026) and symbol and 6 in dynamic:
                # ABS64/GLOB_DAT/JUMP_SLOT can be resolved when their symbol is
                # defined in this image. Undefined external imports stay explicit.
                _, _, _, section_index, value, _ = unpack("<IBBHQQ", dynamic[6] + symbol * 24)
                if section_index != 0:
                    data, offset = locate(target)
                    struct.pack_into("<Q", data, offset, (value + addend) & 0xFFFFFFFFFFFFFFFF)
                    resolved_symbol_relocations += 1
                else:
                    unresolved.append({"address": target, "kind": kind, "symbol": symbol, "addend": addend})
            else:
                unresolved.append({"address": target, "kind": kind, "symbol": symbol, "addend": addend})

    # Preserve the import names for unresolved external relocations. Their
    # addresses remain unresolved; native code or licenses are not emulated.
    for item in unresolved:
        if item["symbol"] and 6 in dynamic and 5 in dynamic:
            name_offset = unpack("<I", dynamic[6] + item["symbol"] * 24)[0]
            data, offset = locate(dynamic[5] + name_offset, 1)
            end = data.find(0, offset)
            if end < 0:
                raise ValueError("Unterminated dynamic symbol name")
            item["name"] = bytes(data[offset:end]).decode("utf-8", errors="replace")
    print(f"RELOCATIONS {dict(relocations)}; {resolved_symbol_relocations} defined-symbol entries resolved; "
          f"{len(unresolved)} external/other entries retained", flush=True)

    bss_size = struct.unpack_from("<I", original, 0x3C)[0]
    file_image = bytearray(0x1000)
    sections = []
    phdrs = []
    for index, segment in enumerate(segments):
        offset = align(len(file_image))
        file_image.extend(b"\0" * (offset - len(file_image)))
        file_image.extend(segment["contents"])
        mem_size = segment["size"] + (bss_size if index == 2 else 0)
        phdrs.append(struct.pack("<IIQQQQQQ", 1, (5, 4, 6)[index], offset,
                                segment["address"], segment["address"], segment["size"], mem_size, 0x1000))
        sections.append((segment["name"], 1, (6, 2, 3)[index], segment["address"],
                         offset, segment["size"], 0, 0, 16, 0))
    data_end = segments[-1]["address"] + segments[-1]["size"]
    sections.append((".bss", 8, 3, data_end, len(file_image), bss_size, 0, 0, 8, 0))
    names = b"\0" + b"\0".join(name.encode() for name in (".text", ".rodata", ".data", ".bss", ".shstrtab")) + b"\0"
    names_offset = len(file_image)
    file_image.extend(names)
    sections.append((".shstrtab", 3, 0, 0, names_offset, len(names), 0, 0, 1, 0))
    shoff = align(len(file_image), 8)
    file_image.extend(b"\0" * (shoff - len(file_image)))
    file_image.extend(b"\0" * 64)
    for section in sections:
        name, *fields = section
        file_image.extend(struct.pack("<IIQQQQIIQQ", names.index(name.encode() + b"\0"), *fields))
    ident = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    file_image[:64] = struct.pack("<16sHHIQQQIHHHHHH", ident, 2, 183, 1, TARGETS[0],
                                 64, shoff, 0, 64, len(phdrs[0]), len(phdrs), 64, len(sections) + 1, len(sections))
    file_image[64:64 + len(phdrs) * 56] = b"".join(phdrs)

    metadata = json.loads((DUMP / "script.json").read_text(encoding="utf-8"))
    by_address = {}
    for method in metadata["ScriptMethod"]:
        by_address.setdefault(method["Address"], []).append(method)
    manifest = {
        "source": str(BUILD / "exefs/main"), "source_sha256": digest(original),
        "metadata": str(BUILD / "romfs/Data/Managed/Metadata/global-metadata.dat"),
        "metadata_sha256": digest((BUILD / "romfs/Data/Managed/Metadata/global-metadata.dat").read_bytes()),
        "script_json": str(DUMP / "script.json"), "script_json_sha256": digest((DUMP / "script.json").read_bytes()),
        "elf_sha256": digest(file_image), "image_base": 0,
        "segments": [{k: v for k, v in s.items() if k != "contents"} for s in segments],
        "relocations": dict(relocations), "resolved_symbol_relocations": resolved_symbol_relocations,
        "unresolved_relocations": unresolved,
        "targets": [{"address": address, "methods": by_address[address]} for address in TARGETS],
        "limitations": ["Derived ELF is an analysis container only", "External relocations remain unresolved",
                        "Generic native addresses may have multiple managed names"],
    }
    output.mkdir(parents=True)
    (output / "switch-main.elf").write_bytes(file_image)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"READY {output / 'switch-main.elf'}", flush=True)


if __name__ == "__main__":
    main()
