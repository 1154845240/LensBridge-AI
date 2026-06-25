import json
import tempfile
from pathlib import Path

from server import file_cleanup


def main():
    assert file_cleanup.parse_image_filenames("single.png") == ["single.png"]
    assert file_cleanup.parse_image_filenames(
        json.dumps(["one.png", "two.png"])
    ) == ["one.png", "two.png"]
    assert file_cleanup.parse_image_filenames("../outside.png") == []

    with tempfile.TemporaryDirectory() as temp_dir:
        upload_dir = Path(temp_dir)
        for filename in ("used.png", "orphan.png", "multi-a.png", "multi-b.png"):
            (upload_dir / filename).write_bytes(b"test")

        orphans, deleted, errors = file_cleanup.cleanup_orphan_uploads(
            upload_dir,
            ["used.png", json.dumps(["multi-a.png", "multi-b.png"])],
        )
        assert orphans == ["orphan.png"]
        assert deleted == 1
        assert errors == []

        deleted, errors = file_cleanup.delete_upload_files(
            upload_dir,
            [json.dumps(["multi-a.png", "multi-b.png"])],
        )
        assert deleted == 2
        assert errors == []

    print("File cleanup test OK")


if __name__ == "__main__":
    main()
