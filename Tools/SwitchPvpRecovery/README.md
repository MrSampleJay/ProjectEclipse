# Switch PvP native recovery with IDA

Verified on September 16, 2026 with the installed IDA Professional
9.1.250226, ARM64 Hex-Rays 9.1.0.250226, and Python 3.12 on Windows.
The final run decompiled all 14 selected functions. This uses IDA's local
`idalib` Python interface; no MCP server or network service is required.

## Run

From `ExportedProject`, choose a new output directory:

```powershell
py -V:3.12 Tools/SwitchPvpRecovery/prepare_image.py --output Temp/SwitchPvpIDA-example
py -V:3.12 Tools/SwitchPvpRecovery/recover_ida.py --image-dir Temp/SwitchPvpIDA-example
```

The default installation is `C:\Program Files\IDA Professional 9.1`.
Override it with `--ida-dir`. The scripts import the installed
`idalib/python/idapro` package directly, without installing Python packages or
changing IDA's installed files. IDA's own first import may create its normal
user configuration file if it does not already exist.

`prepare_image.py` refuses an existing output directory. `recover_ida.py`
reuses the database belonging to its output image and refreshes that run's text
exports. Use a new output directory to preserve earlier evidence. Do not have
that same database open in the GUI while running the recovery script.

For a backend check, add `--smoke` to recover only `HaveSecondPlayer` and
`CompareSingle`. Do not pass `-a` through `open_database` on this installation:
that invocation produced IDA internal error 30602. The working path calls
`open_database(path, False)` and performs explicit analysis of selected ranges.

## Inputs and outputs

Inputs are the extracted Switch v1.1.0 `program/exefs/main`, its
`program/romfs/Data/Managed/Metadata/global-metadata.dat`, and the matching
Il2CppDumper `script.json` under
`ResearchSources/reversingsf2/decompilation/`.

The preparation checks the NSO header and SHA-256 of all three decompressed
segments. It preserves their relative virtual addresses, applies relative
relocations to a derived image at base zero, and exports an ARM64 ELF that IDA
can load with its standard ELF loader. This is an analysis container, not a
runnable game executable. The original NSO and metadata are never modified.

The tested binary had 397,009 relative relocations and 1,959 other relocation
entries. Those other entries referred to undefined external symbols and were
retained as unresolved in the manifest. The preparation also supports resolving
ABS64/GLOB_DAT/JUMP_SLOT entries when their symbols are defined in the image.

Each run contains:

| File | Purpose |
| --- | --- |
| `manifest.json` | Original input hashes, verified segment hashes, relocation accounting, and selected addresses. |
| `switch-main.elf` | Derived image with original RVA layout. |
| `switch-main.elf.i64` | IDA database; open this in IDA to inspect the functions. |
| `<RVA>_<method>.asm` | IDA's disassembly for each target. |
| `<RVA>_<method>.c` | Hex-Rays pseudocode for each successfully decompiled target. |
| `applied-types.h` | Partial, metadata-derived structures and forward declarations used for analysis. |
| `ida-report.json` | Per-function outcome, generated ABI declarations, code references, and limits. |

The final verified run is in `Temp/SwitchPvpIDA-20260916-final/`.
Research images, databases, and exports remain ignored by Git.

## Recovered functions

| RVA | Function |
| --- | --- |
| `D94FD0` | `PvpScene.get_HaveSecondPlayer` |
| `EB6EF0` | `PvpRule.CompareSingle` |
| `C92600` | `InputData.IsInputEqual` |
| `D97430` | `PvpScene.SwitchInputToNextDevice` |
| `D97260` | `PvpScene.SwitchToNextNotOwnedDevice` |
| `D96FB0` | `PvpScene.GetModelParameters` |
| `D44F00` | `GameUtils.CreateFightPVP` |
| `C927A0` | `InputSelector.SetModelInput(InputData)` |
| `C92B60` | `InputSelector.GetModelTeam` |
| `C92950` | `InputSelector.GetModel` |
| `D96C50` | `PvpScene.GetLocationNode` |
| `D961F0` | `PvpScene.StartFight` |
| `E51A20` | `EndPvpFightScreen.ReplayHandler` |
| `E51760` | `EndPvpFightScreen.CloseHandler` |

## Assembly-reviewed observations

`InputData.IsInputEqual` compares only `InputType` at offset `0x14` and
`ControlIndex` at `0x18`; it ignores `Team`. Device cycling advances keyboard
index 0 to keyboard index 1, then gamepad index 0, subsequent gamepads, and back
to keyboard index 0. The exclusive-device helper repeats that advancement while
the result equals the other player's input assignment. This establishes the
native cycling logic, not that every shipped UI exposes both keyboard slots.
`HaveSecondPlayer` separately returns whether the gamepad device count is above 1.

`GetModelParameters` resolves the selected template, obtains PvP settings, calls
`ListSF.ParseUser`, copies the template's `Avatar` and `FirstName`, and uses
`CharacterSelectModule.GetPlayerWeapon` for the requested player.

`CreateFightPVP` prepares `PlayersTotal[0]` with `SetModelParameters` and registers
both player input assignments through `InputSelector`. When the gamepad count is
at least two, the instructions at `D45084` through `D4508C` set the first enemy's
`IsPlayer=true`, `AiControlled=false`, and `UserControlled=true`. The halfword
store at offset `0x61` writes the first two flags together. This is an actual
Switch behavior difference requiring a broader side-semantics audit before any
port into Eclipse.

`ReplayHandler` calls native `Fight.RestartFight` and destroys its result-screen
object. `PvpScene.StartFight` obtains or creates a roster fight and calls
`UserDataWriter.Save` before entering the fight module. These observations do not
justify replacing Eclipse's deliberate disposable-profile policy with the
Switch's persistence behavior.

## Interpretation limits

The output is native pseudocode, not recovered original C# source text. Method
names and field layouts come from the matching metadata; selected native bodies
provide the behavioral evidence. This is targeted analysis, not a full-program
reconstruction or a Switch runtime playtest.

Multiple managed generic methods can share one native address. Such addresses
are named `SharedManagedMethod_<RVA>` and retain their aliases in comments.
The tool does not apply a single concrete generic signature to them. Runtime
helpers, indirect calls, and shared generics can still have incorrect inferred
argument lists in pseudocode. Cross-check them against assembly and register
usage before translating them into gameplay code. Unknown structure fields stay
as padding. The old IL2CPP metadata's leading static `__this` placeholder is
preserved in generated ABI declarations rather than dropped as modern C# would
suggest.
