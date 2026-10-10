# Request: complete held-key state in Processing → Drivers

Status: proposed for shared-contract integration; the local Driver ABI v3
implementation exists, but `Contracts/README.md` remains integration-owned.

## Proposed ControlFrame field

Add an optional `keys` object whose values are binary `0`/`1` levels:

```json
{
  "keys": {
    "w": 1,
    "a": 0,
    "s": 0,
    "d": 0,
    "space": 0,
    "left_shift": 1
  }
}
```

The object is a complete state snapshot and should be present on every frame
while any key may be held. A `1` means keep that key down; `0` or an omitted key
means release it. If the entire optional object is absent, Drivers should
interpret it as all keys released, preserving existing producers' behavior.
Processing owns gesture detection, filtering, key mapping, and deciding when a
level changes. Drivers only translate those levels into OS key-down/key-up
events; they must not infer repeats or add dwell behavior.

The initial set is W, A, S, D, Space, and left Shift. Repeated frames with an
unchanged state do not emit repeated key-downs. Clearing a key emits one key-up.
Pause, disabled output, stale input, backend errors, and teardown release every
held key. To prevent surprising input on arm, the first enabled frame must have
all key levels clear.

## Local Driver ABI mapping

The prototype ABI v3 uses the `fid_frame.keys_down` bitmask:

| Contract name | C constant | Bit |
|---|---|---:|
| `w` | `FID_KEY_W` | `1 << 0` |
| `a` | `FID_KEY_A` | `1 << 1` |
| `s` | `FID_KEY_S` | `1 << 2` |
| `d` | `FID_KEY_D` | `1 << 3` |
| `space` | `FID_KEY_SPACE` | `1 << 4` |
| `left_shift` | `FID_KEY_LEFT_SHIFT` | `1 << 5` |

These local ABI names do not force a change to the shared schema. Coordinate
with the contract/integration owner before adopting field names or semantics
across components. Do not edit the integration-owned `Contracts/README.md` from
the Drivers lane.
