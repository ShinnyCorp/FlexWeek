# Desktop adapters, part C: `custom_look` and `tokens`

Every function in the two modules, as it stands after E6. ADAPTER: encodes, makes one engine call, decodes.
LOGIC: still decides or computes in Python (the reason says why). STAYS: Qt, files, the clock, the
environment, randomness, or a dataclass or exception definition.

## `desktop/native/custom_look.py`

| module | function | class | reason |
|---|---|---|---|
| custom_look | `LookNameError` | STAYS | exception definition; raised from the engine's `LookNameProblem` |
| custom_look | `_text_or_none` | ADAPTER | turns a value that is not text into none, as the engine takes a pack and an accent |
| custom_look | `base_of` | ADAPTER | one call, `look_base_of` |
| custom_look | `start_custom` | ADAPTER | one call, `look_start` |
| custom_look | `wear` | ADAPTER | one call, `look_wear` |
| custom_look | `reset_look` | ADAPTER | one call, `look_reset` |
| custom_look | `_name` | ADAPTER | one call, `look_name`; the engine's error becomes `LookNameError` |
| custom_look | `_find` | ADAPTER | one call, `look_find` |
| custom_look | `sanitize_saved` | ADAPTER | one call, `look_saved` |
| custom_look | `save_look` | ADAPTER | one call, `look_save`; the engine's error becomes `LookNameError` |
| custom_look | `free_name` | ADAPTER | one call, `free_name`; the engine's error becomes `LookNameError` |
| custom_look | `rename_look` | ADAPTER | one call, `rename_look`; the engine's error becomes `LookNameError` |
| custom_look | `duplicate_look` | ADAPTER | one call, `duplicate_look`; the engine's error becomes `LookNameError` |
| custom_look | `delete_look` | ADAPTER | one call, `delete_look`; the engine's error becomes `LookNameError` |
| custom_look | `export_look` | ADAPTER | one call, `look_export` |
| custom_look | `Imported` | STAYS | dataclass |
| custom_look | `import_look` | STAYS | reads the file's text with Python's own JSON reader (NaN, Infinity, huge integers and lone surrogates are Python-only) and passes the value on; its size guard keeps a file the engine refuses from being parsed. Not one of the three reasons, see the report |
| custom_look | `Problem` | STAYS | dataclass |
| custom_look | `readability` | LOGIC | the checks, the filter on blocks drawn in their own fill, and the labels are in the engine; what stays is the loop that asks `look.py` for each category's palette and block paint, because `resolved_palette`, `category_paint` and `block_paint` are not in the engine. It ends when those move |
| custom_look | `apply_fix` | ADAPTER | one call, `look_apply_fix`; the engine reads the problem's own fields |

Moved by E6 into `engine/engine/src/desk/custom_look.rs`:

- `_finite` and `_readable` (a NaN or Infinity read as an empty list, except under `base`): `readable` and
  `finite`, run first by `import_look`.
- the `drawn["fill"] == fill` filter and the category labels in `readability`: `filled_blocks`.

## `desktop/native/tokens.py`

Nothing moved. Every function was an adapter already.

| module | function | class | reason |
|---|---|---|---|
| tokens | `Shadow` | STAYS | dataclass |
| tokens | `type_pt` | ADAPTER | one call, `tokens_type_pt` |
| tokens | `text_knob` | ADAPTER | one call, `tokens_text_knob` |
| tokens | `linear_rgb` | ADAPTER | one call; the list becomes a tuple |
| tokens | `hex_from_linear` | ADAPTER | one call |
| tokens | `oklab_from_linear` | ADAPTER | one call; the list becomes a tuple |
| tokens | `linear_from_oklab` | ADAPTER | one call; the list becomes a tuple |
| tokens | `oklab` | ADAPTER | one call; the list becomes a tuple |
| tokens | `oklch` | ADAPTER | one call |
| tokens | `_channels` | ADAPTER | one call; the list becomes a tuple |
| tokens | `mix` | ADAPTER | one call |
| tokens | `luminance` | ADAPTER | one call |
| tokens | `contrast` | ADAPTER | one call |
| tokens | `oklch_of` | ADAPTER | one call; the list becomes a tuple |
| tokens | `fit_lightness` | ADAPTER | one call; the grounds are written with `plain` |
| tokens | `mix_oklab` | ADAPTER | one call |
| tokens | `family_colours` | ADAPTER | one call; each list in the result becomes a tuple |

The module's tables (`SPACING`, `RADIUS_*`, `SHADOW_*`, `TYPE_PT`, `TEXT_SCALE`, `FILL`, `MARK` and the
rest) are data, not functions. The engine holds its own copies of some of them (`tokens.rs`).
