# Turn-runtime thread config snapshot callability

## Goal segment
- Keep the `track_turn_resolved_config` analytics payload stable when thread config is provided via
  `session.thread.thread_config_snapshot`.

## Decision
- Treat `session.thread.thread_config_snapshot` as possibly callable and resolve it through `_maybe_await`
  in the same way as the direct `session.thread_config_snapshot` path.

## Rationale
- Some session/thread implementations expose the snapshot as a provider callable instead of a plain object.
- The fallback path previously returned the callable object directly, producing invalid analytics payloads.

## Behavior
- `thread_config_snapshot` callable -> resolved and awaited as needed.
- `thread_config_snapshot` non-callable -> used directly.
