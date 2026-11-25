"""Сохранить чертежи схем 1–25 из PDF задания без изменения исходника."""

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


def extract(pdf: Path, output: Path, pdftoppm: str = "pdftoppm") -> None:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        for page in range(36, 50):
            target = Path(temporary) / "page"
            subprocess.run(
                [pdftoppm, "-f", str(page), "-l", str(page), "-scale-to", "1800", "-png", "-singlefile", str(pdf), str(target)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            image = Image.open(target.with_suffix(".png")).convert("RGB")
            if page <= 47 and image.height > image.width:
                image = image.rotate(-90, expand=True)
            width, height = image.size
            if page <= 46:
                # На каждой из этих страниц по два чертежа, разделённых рамкой.
                for side in (0, 1):
                    number = 2 * (page - 36) + side + 1
                    x0, x1 = (0.105, 0.50) if side == 0 else (0.50, 0.90)
                    crop = image.crop((round(width * x0), round(height * 0.11), round(width * x1), round(height * 0.86)))
                    crop.save(output / f"{number}.png", optimize=True)
            elif page == 47:
                image.crop((round(width * 0.10), round(height * 0.11), round(width * 0.51), round(height * 0.86))).save(output / "23.png", optimize=True)
            else:
                image.crop((round(width * 0.13), round(height * 0.08), round(width * 0.87), round(height * 0.91))).save(output / f"{page-24}.png", optimize=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pdftoppm", default="pdftoppm")
    args = parser.parse_args()
    extract(args.pdf, args.output, args.pdftoppm)
