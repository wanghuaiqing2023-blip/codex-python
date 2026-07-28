"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

EXTENSIONS_FOLDER_STRUCTURE = '\nMemory extensions (under {{ memory_extensions_root }}/):\n\n- <extension_name>/instructions.md\n  - Source-specific guidance for interpreting additional memory signals. If an\n    extension folder exists, you must read its instructions.md to determine how to use this memory\n    source.\n\nIf the user has any memory extensions, you MUST read the instructions for each extension to\ndetermine how to use the memory source. If the workspace diff shows deleted extension resource files,\nremove stale memories derived only from those resources. If it has no extension folders, continue\nwith the standard memory inputs only.\n'


EXTENSIONS_PRIMARY_INPUTS = "\nOptional source-specific inputs:\nUnder `{{ memory_extensions_root }}/`:\n\n- `<extension_name>/instructions.md`\n  - If extension folders exist, read each instructions.md first and follow it when interpreting\n    that extension's memory source.\n\nIf the workspace diff shows deleted memory extension resources, use that extension-specific deletion\nsignal to remove stale memories derived only from those resources.\n"
