"""
Move page OCR XML files from:
  data/additional_ocr/{id}/BandXX_chunkXXX/page/00XX_p0XX.xml
to:
  data/extracted/BandXX_chunkXXX/add_ocr/00XX_p0XX.xml

Move txt files from:
  data/additional_ocr/{id}/BandXX_chunkXXX/txt/00XX_p0XX.txt
to:
  data/extracted/BandXX_chunkXXX/add_txt/00XX_p0XX.txt
"""

import shutil
from pathlib import Path


def move_additional_ocr(base_dir: Path) -> None:
    additional_ocr_dir = base_dir / "data" / "additional_ocr"
    extracted_dir = base_dir / "data" / "extracted"

    moved = 0
    skipped = 0
    errors = 0

    for id_dir in additional_ocr_dir.iterdir():
        if not id_dir.is_dir():
            continue
        for chunk_dir in id_dir.iterdir():
            if not chunk_dir.is_dir():
                continue
            chunk_name = chunk_dir.name  # e.g. Band08_chunk006

            for src_folder, target_folder, glob_pattern in [
                ("page", "add_ocr", "*.xml"),
                ("txt", "add_txt", "*.txt"),
            ]:
                src_dir = chunk_dir / src_folder
                if not src_dir.exists():
                    continue
                target_dir = extracted_dir / chunk_name / target_folder
                target_dir.mkdir(parents=True, exist_ok=True)
                for src_file in src_dir.glob(glob_pattern):
                    target_file = target_dir / src_file.name
                    if target_file.exists():
                        print(f"SKIP (already exists): {target_file}")
                        skipped += 1
                        continue
                    try:
                        shutil.move(str(src_file), str(target_file))
                        print(f"MOVED: {src_file} -> {target_file}")
                        moved += 1
                    except Exception as e:
                        print(f"ERROR moving {src_file}: {e}")
                        errors += 1

    print(f"\nDone: {moved} moved, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    move_additional_ocr(base_dir)
