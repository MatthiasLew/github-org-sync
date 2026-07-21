import struct
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def compile_pngs_to_ico(png_paths: list[Path], ico_path: Path) -> None:
    """Compiles multiple PNG files into a single multi-resolution ICO file."""
    png_datas = []
    for path in png_paths:
        with path.open("rb") as f:
            png_datas.append(f.read())

    num_images = len(png_paths)
    header = struct.pack("<HHH", 0, 1, num_images)

    current_offset = 6 + 16 * num_images
    entries = []

    for i, path in enumerate(png_paths):
        size = int(path.stem.split("-")[1])
        width = 0 if size == 256 else size
        height = 0 if size == 256 else size
        color_count = 0
        reserved = 0
        planes = 1
        bit_count = 32
        data_size = len(png_datas[i])

        entry = struct.pack(
            "<BBBBHHII",
            width,
            height,
            color_count,
            reserved,
            planes,
            bit_count,
            data_size,
            current_offset,
        )
        entries.append(entry)
        current_offset += data_size

    with ico_path.open("wb") as f:
        f.write(header)
        for entry in entries:
            f.write(entry)
        for data in png_datas:
            f.write(data)

    print(f"Compiled multi-resolution icon to {ico_path}")


def main() -> None:
    # Requires QGuiApplication to initialize rendering system
    _app = QGuiApplication(sys.argv)

    svg_path = Path("assets/logo.svg")
    if not svg_path.exists():
        print("Error: assets/logo.svg not found")
        sys.exit(1)

    icons_dir = Path("assets/icons")
    icons_dir.mkdir(parents=True, exist_ok=True)

    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        print("Error: Invalid SVG file")
        sys.exit(1)

    sizes = [16, 32, 48, 128, 256]
    png_paths = []

    for size in sizes:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()

        out_path = icons_dir / f"app-{size}.png"
        image.save(str(out_path), "PNG")
        print(f"Saved {out_path}")
        png_paths.append(out_path)

    ico_path = Path("assets/github-org-sync.ico")
    compile_pngs_to_ico(png_paths, ico_path)


if __name__ == "__main__":
    main()
