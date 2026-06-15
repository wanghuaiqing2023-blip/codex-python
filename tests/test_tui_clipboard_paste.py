from pathlib import Path

import pycodex.tui.clipboard_paste as clipboard_paste
from pycodex.tui.clipboard_paste import (
    EncodedImageFormat,
    PasteImageError,
    PasteImageErrorKind,
    PastedImageInfo,
    convert_windows_path_to_wsl,
    fmt,
    paste_image_as_png,
    paste_image_to_temp_png,
    normalize_pasted_path,
    pasted_image_format,
)


PNG_2X3 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x02"
    b"\x00\x00\x00\x03"
    b"\x08\x06\x00\x00\x00"
)


def test_error_display_and_format_labels_match_rust() -> None:
    # Rust source: clipboard_paste.rs Display impl and EncodedImageFormat::label.
    assert fmt(PasteImageError.clipboard_unavailable("denied")) == "clipboard unavailable: denied"
    assert fmt(PasteImageError.no_image("empty")) == "no image on clipboard: empty"
    assert fmt(PasteImageError.encode_failed("bad rgba")) == "could not encode image: bad rgba"
    assert fmt(PasteImageError.io_error("disk")) == "io error: disk"
    assert EncodedImageFormat.PNG.label() == "PNG"
    assert EncodedImageFormat.JPEG.label() == "JPEG"
    assert EncodedImageFormat.OTHER.label() == "IMG"


def test_pasted_image_info_preserves_fields() -> None:
    info = PastedImageInfo(width=10, height=20, encoded_format=EncodedImageFormat.PNG)
    assert info.width == 10
    assert info.height == 20
    assert info.encoded_format is EncodedImageFormat.PNG


def test_normalize_file_url_and_shell_escaped_paths() -> None:
    # Rust tests: normalize_file_url, normalize_shell_escaped_single_path,
    # normalize_simple_quoted_path_fallback, normalize_single_quoted_unix_path.
    assert normalize_pasted_path("file:///tmp/example.png") == Path("/tmp/example.png")
    assert normalize_pasted_path("/home/user/My\\ File.png") == Path("/home/user/My File.png")
    assert normalize_pasted_path('"/home/user/My File.png"') == Path("/home/user/My File.png")
    assert normalize_pasted_path("'/home/user/My File.png'") == Path("/home/user/My File.png")


def test_normalize_multiple_tokens_returns_none() -> None:
    assert normalize_pasted_path("/home/user/a\\ b.png /home/user/c.png") is None


def test_normalize_windows_paths_without_posix_backslash_loss() -> None:
    # Rust tests: quoted/unquoted Windows paths and UNC paths.
    assert normalize_pasted_path(r"C:\Temp\example.png") == Path(r"C:\Temp\example.png")
    assert normalize_pasted_path(r"'C:\Users\Alice\My File.jpeg'") == Path(r"C:\Users\Alice\My File.jpeg")
    assert normalize_pasted_path(r'"C:\Users\Alice\My File.jpeg"') == Path(r"C:\Users\Alice\My File.jpeg")
    assert normalize_pasted_path(r"C:\Users\Alice\My Pictures\example image.png") == Path(
        r"C:\Users\Alice\My Pictures\example image.png"
    )
    assert normalize_pasted_path(r"\\server\share\folder\file.jpg") == Path(r"\\server\share\folder\file.jpg")


def test_convert_windows_path_to_wsl_contract() -> None:
    assert convert_windows_path_to_wsl(r"C:\Users\Alice\Pictures\example image.png") == Path(
        "/mnt/c/Users/Alice/Pictures/example image.png"
    )
    assert convert_windows_path_to_wsl(r"\\server\share\folder\file.jpg") is None
    assert convert_windows_path_to_wsl("not-a-drive") is None


def test_pasted_image_format_png_jpeg_unknown() -> None:
    # Rust tests: pasted_image_format_png_jpeg_unknown and windows-style path variant.
    assert pasted_image_format("/a/b/c.PNG") is EncodedImageFormat.PNG
    assert pasted_image_format("/a/b/c.jpg") is EncodedImageFormat.JPEG
    assert pasted_image_format("/a/b/c.JPEG") is EncodedImageFormat.JPEG
    assert pasted_image_format("/a/b/c") is EncodedImageFormat.OTHER
    assert pasted_image_format("/a/b/c.webp") is EncodedImageFormat.OTHER
    assert pasted_image_format(r"C:\a\b\c.PNG") is EncodedImageFormat.PNG
    assert pasted_image_format(r"C:\a\b\c.jpeg") is EncodedImageFormat.JPEG
    assert pasted_image_format(r"C:\a\b\noext") is EncodedImageFormat.OTHER


def test_convert_windows_path_to_wsl_trims_drive_root_and_empty_components() -> None:
    assert convert_windows_path_to_wsl(r"D:\\") == Path("/mnt/d")
    assert convert_windows_path_to_wsl(
        r"E:/Users//Alice\\Pictures/example.png"
    ) == Path("/mnt/e/Users/Alice/Pictures/example.png")


def test_windows_clipboard_dump_probe_and_temp_file_semantics(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "clipboard.png"
    image_path.write_bytes(PNG_2X3)

    monkeypatch.setattr(clipboard_paste.sys, "platform", "win32")
    monkeypatch.setattr(
        clipboard_paste,
        "try_dump_windows_clipboard_image_with_info",
        lambda: (str(image_path), PastedImageInfo(2, 3, EncodedImageFormat.PNG)),
    )

    png, info = paste_image_as_png()
    assert png == PNG_2X3
    assert info == PastedImageInfo(2, 3, EncodedImageFormat.PNG)

    temp_path, temp_info = paste_image_to_temp_png()
    assert temp_path.name.startswith("codex-clipboard-")
    assert temp_path.suffix == ".png"
    assert temp_path.read_bytes() == PNG_2X3
    assert temp_info == info


def test_wsl_fallback_maps_windows_path_and_probes_png_dimensions(monkeypatch, tmp_path) -> None:
    mapped = tmp_path / "clipboard.png"
    mapped.write_bytes(PNG_2X3)

    monkeypatch.setattr(clipboard_paste, "is_probably_wsl", lambda: True)
    monkeypatch.setattr(
        clipboard_paste,
        "try_dump_windows_clipboard_image_with_info",
        lambda: (r"C:\Temp\clipboard.png", PastedImageInfo(0, 0, EncodedImageFormat.PNG)),
    )
    monkeypatch.setattr(clipboard_paste, "convert_windows_path_to_wsl", lambda path: mapped)

    path, info = clipboard_paste.try_wsl_clipboard_fallback(
        PasteImageError(PasteImageErrorKind.CLIPBOARD_UNAVAILABLE, "x")
    )

    assert path == mapped
    assert info == PastedImageInfo(2, 3, EncodedImageFormat.PNG)


def test_paste_image_as_png_reports_no_image_when_windows_dump_has_no_image(monkeypatch) -> None:
    monkeypatch.setattr(clipboard_paste.sys, "platform", "win32")
    monkeypatch.setattr(clipboard_paste, "try_dump_windows_clipboard_image_with_info", lambda: None)

    try:
        paste_image_as_png()
    except PasteImageError as error:
        assert error.kind is PasteImageErrorKind.NO_IMAGE
        assert str(error) == "no image on clipboard: no image on clipboard"
    else:
        raise AssertionError("expected PasteImageError")
