import json
from pathlib import Path


def parse_image_filenames(value):
    """将数据库中的单文件名或 JSON 数组统一转换为安全文件名列表。"""
    raw = str(value or "").strip()
    if not raw:
        return []

    try:
        values = json.loads(raw) if raw.startswith("[") else [raw]
    except (TypeError, ValueError, json.JSONDecodeError):
        values = [raw]

    filenames = []
    for value in values:
        filename = str(value or "").strip()
        if filename and Path(filename).name == filename:
            filenames.append(filename)
    return filenames


def delete_upload_files(upload_dir, stored_values):
    """删除记录关联的上传文件，返回删除数量和失败信息。"""
    root = Path(upload_dir)
    deleted = 0
    errors = []

    for stored_value in stored_values:
        for filename in parse_image_filenames(stored_value):
            path = root / filename
            try:
                if path.is_file():
                    path.unlink()
                    deleted += 1
            except OSError as exc:
                errors.append(f"{filename}: {exc}")

    return deleted, errors


def cleanup_orphan_uploads(upload_dir, referenced_values):
    """删除上传目录中未被数据库引用的文件。"""
    root = Path(upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    referenced = {
        filename
        for value in referenced_values
        for filename in parse_image_filenames(value)
    }
    orphan_names = sorted(
        path.name
        for path in root.iterdir()
        if path.is_file() and path.name not in referenced
    )
    deleted, errors = delete_upload_files(root, orphan_names)
    return orphan_names, deleted, errors
