# Startup save selection on the exact 1.37.5 build

The supported explicit selector is `-continue=<local-save-basename>.eu4`.
The game prepends `save games/`; do not pass a Windows absolute path or another
`save games/` prefix. This is disk-PE evidence, not a guarantee that the selected
save passes all later startup/load checks.

`8757e0 → 1719120 → 1719300` parses the arguments. `1719470` changes from key to
value at `=`. The key lookup `1719b50` copies the corresponding String32 value.
`8768bc` constructs `save games/`, `8768e9` appends the supplied filename, and
`8768fd` stores the result in global String32 `1fd3a08`. The grammar handles a
single or double leading dash. Filenames used by the research loader remain
restricted to independently verified ASCII test-save basenames.

`-continuelastsave` is a presence-only option. It reads `continue_game.json` first,
then copies the JSON `filename` value without prefixing it. When this succeeds,
flag `233fe9c` causes the later `continue` option to be skipped. Supplying both
therefore does not mean the explicit filename wins.

The JSON reader `5d1670` recognizes string fields `title`, `desc`, `date` and
`filename`, placing them at offsets `0`, `20`, `40`, `60`, with a validity byte at
`80`. The writer `5d1050` emits the same fields using `continue_game.temp` before
replacing `continue_game.json`. An illustrative structure is:

```json
{
  "title": "Research baseline",
  "desc": "France",
  "date": "1444.11.11",
  "filename": "save games/llm_verified_baseline.eu4"
}
```

This document does not authorize rewriting user metadata. The existing metadata
may select an unrelated autosave. The generator reads no user metadata, process
command line or save data.

The path is actually consumed: `204b8e` tests its nonzero length, `204ea4` passes
the String32 to `2111c0`, and that routine checks the VFS path and reads it through
`1710440` before further session/load setup. Argument acceptance should be
distinguished from completed map loading. Steam initialization, mod loading,
save validity and the normal startup sequence still apply.

Reproduce with `python work/trace_startup_continue.py --deps-dir <capstone-dir>`.
The script pins executable SHA256
`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`, follows only
bounded CFGs, and explicitly decodes the command-line character jump table.
`work/reports/native-startup-continue-1375.json` contains 10 function entries and
25,895 decoded bytes; consecutive runs produced SHA256
`84f4f6db297c85706a05e96cac227803f77e38a6d50e750fd7d7b74bdba02035`.
All static findings retain `runtime_verified=false`; later root-agent runtime
observations are separate evidence.
