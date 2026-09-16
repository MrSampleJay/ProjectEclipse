"""Run targeted Hex-Rays recovery through the locally installed IDA library.

Usage: py -V:3.12 Tools/SwitchPvpRecovery/recover_ida.py --image-dir Temp/<run>
The shipped idapro package is imported directly; no MCP server or pip install is
needed. Names and ABI declarations come from this build's script.json. Generic
shared native addresses deliberately retain all aliases without a guessed type.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--ida-dir", type=Path, default=Path(r"C:\Program Files\IDA Professional 9.1"))
    parser.add_argument("--smoke", action="store_true", help="Verify the backend on the two smallest methods")
    args = parser.parse_args()
    directory = args.image_dir.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    elf = directory / "switch-main.elf"
    if hashlib.sha256(elf.read_bytes()).hexdigest() != manifest["elf_sha256"]:
        raise ValueError("Derived ELF no longer matches the verified preparation manifest")
    metadata_path = Path(manifest["script_json"])
    if hashlib.sha256(metadata_path.read_bytes()).hexdigest() != manifest["script_json_sha256"]:
        raise ValueError("Method metadata changed since preparation")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    os.environ["IDADIR"] = str(args.ida_dir)
    sys.path.insert(0, str(args.ida_dir / "idalib/python"))
    # Import before any other IDA module, as required by the local idalib README.
    import idapro
    import ida_auto
    import ida_bytes
    import ida_funcs
    import ida_hexrays
    import ida_ida
    import ida_lines
    import ida_loader
    import ida_name
    import ida_ua
    import idautils
    import idc

    database = elf.with_name(elf.name + ".i64")
    input_path = database if database.exists() else elf
    print(f"OPEN {input_path} using IDA {idapro.get_library_version()}", flush=True)
    idapro.enable_console_messages(True)
    status = idapro.open_database(str(input_path), False)
    if status:
        raise RuntimeError(f"IDA could not open the analysis image: {status}")
    report = {"ida_version": idapro.get_library_version(), "source_sha256": manifest["source_sha256"],
              "elf_sha256": manifest["elf_sha256"], "functions": [], "limitations": manifest["limitations"] + [
                  "Selected functions only; not whole-program analysis",
                  "Partial metadata-derived types; unknown fields remain padding",
                  "Untyped runtime helpers and shared generics may have inaccurate inferred arguments",
                  "Pseudocode requires assembly review before porting behavior"], "signature_failures": []}
    try:
        ida_auto.enable_auto(False)
        if not ida_ida.inf_is_64bit() or ida_ida.inf_get_procname() != "ARM":
            raise RuntimeError(f"Wrong processor: {ida_ida.inf_get_procname()}, 64-bit={ida_ida.inf_is_64bit()}")
        ida_loader.load_plugin("hexarm")
        if not ida_hexrays.init_hexrays_plugin():
            raise RuntimeError("ARM Hex-Rays decompiler initialization failed")
        print("BACKEND_READY ARM64 Hex-Rays " + ida_hexrays.get_hexrays_version(), flush=True)
        report["hexrays_version"] = ida_hexrays.get_hexrays_version()
        methods = {}
        for method in metadata["ScriptMethod"]:
            methods.setdefault(method["Address"], []).append(method)
        addresses = sorted(set(metadata["Addresses"]) | set(methods))

        def safe(name: str) -> str:
            return re.sub(r"[^A-Za-z0-9_]", "_", name)[:180]

        for address, aliases in methods.items():
            if not ida_bytes.is_mapped(address):
                continue
            name = safe(aliases[0]["Name"]) if len(aliases) == 1 else f"SharedManagedMethod_{address:X}"
            ida_name.set_name(address, f"{name}__{address:X}", ida_name.SN_NOWARN | ida_name.SN_NOCHECK)
            ida_bytes.set_cmt(address, "\n".join(item["Signature"] for item in aliases), True)
        for entry in metadata["ScriptMetadata"] + metadata["ScriptMetadataMethod"]:
            address = entry["Address"]
            if ida_bytes.is_mapped(address):
                ida_bytes.create_qword(address, 8)
                ida_name.set_name(address, safe(entry["Name"]) + f"__{address:X}", ida_name.SN_NOWARN)
                ida_bytes.set_cmt(address, entry["Name"], True)
        for entry in metadata["ScriptString"]:
            address = entry["Address"]
            if ida_bytes.is_mapped(address):
                value = entry["Value"]
                ida_bytes.create_qword(address, 8)
                ida_name.set_name(address, "Literal_" + safe(value)[:65] + f"__{address:X}", ida_name.SN_NOWARN)
                ida_bytes.set_cmt(address, json.dumps(value, ensure_ascii=True), True)

        # Partial structures: every named offset below is recorded in dump.cs.
        # Unrecovered areas remain explicit padding instead of invented fields.
        declarations = """
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;
typedef unsigned long long uint64_t;
typedef signed char int8_t;
typedef short int16_t;
typedef int int32_t;
typedef long long int64_t;
typedef unsigned long long uintptr_t;
typedef long long intptr_t;
struct MethodInfo;
struct Il2CppObject;
struct System_String_o;
struct Nekki_SF2_Core_Fights_Model_Support_ModelParameters_o;
struct System_Collections_Generic_List_ModelParameters__o;
#pragma pack(push, 1)
struct Nekki_SF2_Core_Fights_Controls_InputData_o {
  void *klass; void *monitor; int32_t Team; int32_t InputType; int32_t ControlIndex;
};
struct Nekki_SF2_Core_Fights_Model_Support_ModelParameters_o {
  uint8_t _unknown0[0x61]; bool IsPlayer; bool AiControlled; bool UserControlled;
  uint8_t _unknown64[0xA0-0x64]; void *ItemSkeleton; void *ItemWeapon;
  uint8_t _unknownB0[0x118-0xB0]; System_String_o *FirstName; System_String_o *LastName; System_String_o *Avatar;
};
struct Nekki_SF2_Core_Zones_FightList_o {
  uint8_t _unknown0[0x38]; System_String_o *Location;
  uint8_t _unknown40[0xF8-0x40]; System_Collections_Generic_List_ModelParameters__o *PlayersTotal;
  System_Collections_Generic_List_ModelParameters__o *EnemiesTotal;
};
struct Nekki_SF2_Core_API_ListSF_TemplateUser_o {
  void *klass; void *monitor; Nekki_SF2_Core_Fights_Model_Support_ModelParameters_o *ModelParameters;
};
struct Nekki_SF2_GUI_Pvp_PvpScene_o {
  uint8_t _unknown0[0x88]; void *CharacterModule;
  uint8_t _unknown90[0xA0-0x90]; System_String_o *FirstTemplate; System_String_o *SecondTemplate;
  System_String_o *LocationTemplate;
};
#pragma pack(pop)
"""
        # Forward declarations preserve pointer ABI for other managed types.
        pointer_types = set()
        for method in metadata["ScriptMethod"]:
            pointer_types.update(re.findall(r"\b([A-Za-z_]\w*)\s*\*", method["Signature"]))
        builtin = {"void", "char", "bool", "float", "double", "int", "short", "long",
                   "int8_t", "int16_t", "int32_t", "int64_t", "uint8_t", "uint16_t", "uint32_t", "uint64_t", "intptr_t", "uintptr_t"}
        declarations += "\n".join(f"struct {name};" for name in sorted(pointer_types - builtin))
        errors = idc.parse_decls(declarations, idc.PT_SILENT)
        report["type_parse_errors"] = errors
        if errors:
            raise RuntimeError(f"Partial type declarations could not be parsed: {errors}")
        (directory / "applied-types.h").write_text(declarations, encoding="utf-8")
        targets = manifest["targets"][:2] if args.smoke else manifest["targets"]
        for entry in targets:
            address = entry["address"]
            index = bisect.bisect_right(addresses, address)
            end = addresses[index]
            if end - address > 0x10000:
                raise RuntimeError(f"Unbounded target function 0x{address:X}")
            for instruction in range(address, end, 4):
                ida_ua.create_insn(instruction)
            if ida_funcs.get_func(address) is None and not ida_funcs.add_func(address, end):
                raise RuntimeError(f"Could not create function at 0x{address:X}")
            # Assign exact generated ABI at unique callees and root. Do not force
            # one closed generic signature onto an address shared by many types.
            called = set()
            for instruction in idautils.FuncItems(address):
                called.update(idautils.CodeRefsFrom(instruction, False))
            for callee in called | {address}:
                aliases = methods.get(callee, [])
                if len(aliases) == 1:
                    signature = aliases[0]["Signature"]
                    if not idc.SetType(callee, signature):
                        report["signature_failures"].append({"address": callee, "signature": signature})
                        if callee == address:
                            raise RuntimeError(f"Could not apply root ABI at 0x{address:X}")
            ida_auto.enable_auto(True)
            ida_auto.plan_and_wait(address, end)
            ida_auto.enable_auto(False)
            name = entry["methods"][0]["Name"]
            filename = f"{address:08X}_{safe(name)}"
            print(f"DECOMPILE 0x{address:X} {name}", flush=True)
            disassembly = []
            for instruction in idautils.FuncItems(address):
                line = ida_lines.tag_remove(idc.generate_disasm_line(instruction, 0) or "")
                disassembly.append(f"{instruction:08X}  {line}")
            (directory / (filename + ".asm")).write_text("\n".join(disassembly) + "\n", encoding="utf-8")
            result = {"address": address, "name": name, "native_end": end, "assembly": filename + ".asm",
                      "aliases": entry["methods"], "direct_code_refs": sorted(called)}
            try:
                cfunc = ida_hexrays.decompile(address)
                if cfunc is None:
                    raise RuntimeError("Decompiler returned no function")
                pseudo = "\n".join(ida_lines.tag_remove(line.line) for line in cfunc.get_pseudocode())
                (directory / (filename + ".c")).write_text(pseudo + "\n", encoding="utf-8")
                result.update(success=True, pseudocode=filename + ".c")
                print(f"RECOVERED {len(pseudo.splitlines())} pseudocode lines", flush=True)
            except Exception as error:
                result.update(success=False, error=str(error))
                print("FAILED " + str(error), flush=True)
            report["functions"].append(result)
            (directory / "ida-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["success"] = all(item["success"] for item in report["functions"])
        (directory / "ida-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"RESULT {sum(item['success'] for item in report['functions'])}/{len(targets)} native functions decompiled", flush=True)
        if not report["success"]:
            raise RuntimeError("One or more native functions failed; inspect ida-report.json")
    finally:
        ida_auto.enable_auto(False)
        idapro.close_database(True)


if __name__ == "__main__":
    main()
