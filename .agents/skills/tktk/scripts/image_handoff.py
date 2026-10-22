"""Persist built-in image results per job; never call an image service."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    if value is not None and datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('Timestamps must include a timezone')
    return value


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def image_path(value):
    if not value or not Path(value).is_absolute():
        raise ValueError('Image reference must be a nonempty absolute path')
    path = Path(value).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Image reference is not a file')
    with path.open('rb') as handle:
        header = handle.read(16)
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        extension = '.png'
    elif header.startswith(b'\xff\xd8\xff'):
        extension = '.jpg'
    elif header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        extension = '.webp'
    else:
        raise ValueError('Expected a PNG, JPEG or WebP signature; not a visual-quality check')
    return path, extension


def job_id(value):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value):
        raise ValueError('Use a unique lowercase job id: product-page-attempt, without paths')
    if re.fullmatch(r'(con|prn|aux|nul|com[1-9]|lpt[1-9])', value):
        raise ValueError('Reserved Windows filename')
    return value


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Task path escapes the specified output directory')
    return path


def atomic_json(path, data):
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(root, identifier):
    lock = inside(root, f'.tktk/jobs/{identifier}.lock')
    try:
        with lock.open('x', encoding='utf-8') as handle:
            handle.write(str(os.getpid()))
    except FileExistsError:
        raise ValueError('Handoff job is busy or has a stale lock; inspect it, do not regenerate the image')
    try:
        yield
    finally:
        lock.unlink()


def read_job(root, identifier):
    return json.loads(inside(root, f'.tktk/jobs/{job_id(identifier)}.json').read_text(encoding='utf-8'))


def run(args):
    if not Path(args.task_dir).is_absolute():
        raise ValueError('task-dir must be absolute')
    root = Path(args.task_dir).resolve()
    for subdir in ('.tktk/jobs', '.tktk/results'):
        inside(root, subdir).mkdir(parents=True, exist_ok=True)
    if args.command == 'check-inputs':
        product, _ = image_path(args.product)
        references = [str(product)]
        for identifier in args.anchor_job:
            record = read_job(root, identifier)
            if record['status'] != 'accepted':
                raise ValueError(f'Anchor {identifier} has not passed visual review')
            anchor, _ = image_path(record['saved_image'])
            if not anchor.is_relative_to(root) or digest(anchor) != record['sha256']:
                raise ValueError('Accepted anchor changed or is outside this task')
            if str(anchor) not in references:
                references.append(str(anchor))
        return {'ready': True, 'referenced_image_paths': references}

    identifier = job_id(args.job_id)
    record_path = inside(root, f'.tktk/jobs/{identifier}.json')
    with locked(root, identifier):
        if args.command == 'receive':
            source, extension = image_path(args.source)
            sha = digest(source)
            if record_path.exists():
                existing = read_job(root, identifier)
                if existing['sha256'] != sha:
                    raise ValueError('Job already has a different result; use a new attempt id')
                saved, _ = image_path(existing['saved_image'])
                if not saved.is_relative_to(root) or digest(saved) != sha:
                    raise ValueError('Previously saved result changed; inspect before recovering')
                return existing  # Idempotent receipt must not reset review or timestamps.
            submitted = timestamp(args.submitted_at)
            returned = timestamp(args.returned_at)
            if submitted and returned and datetime.fromisoformat(returned.replace('Z', '+00:00')) < datetime.fromisoformat(submitted.replace('Z', '+00:00')):
                raise ValueError('returned-at precedes submitted-at')
            target = inside(root, f'.tktk/results/{identifier}{extension}')
            if target.exists() and digest(target) != sha:
                raise ValueError('Orphan result differs; inspect before recovering')
            if not target.exists():
                shutil.copyfile(source, target)
            if digest(target) != sha:
                raise ValueError('Copied image hash mismatch')
            record = {'job_id': identifier, 'status': 'generated_pending_review',
                      'source_image': str(source), 'saved_image': str(target), 'sha256': sha,
                      'submitted_at': submitted, 'returned_at': returned,
                      'received_at': now(), 'reviewed_at': None, 'review_note': None}
        else:
            record = read_job(root, identifier)
            saved, _ = image_path(record['saved_image'])
            if not saved.is_relative_to(root) or digest(saved) != record['sha256']:
                raise ValueError('Result changed since receipt; inspect it before review')
            if not args.note.strip():
                raise ValueError('Record a concrete visual-review reason')
            record.update(status=args.status, reviewed_at=now(), review_note=args.note.strip())
        atomic_json(record_path, record)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-dir', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check-inputs')
    check.add_argument('--product', required=True)
    check.add_argument('--anchor-job', action='append', default=[])
    receive = commands.add_parser('receive')
    receive.add_argument('--job-id', required=True)
    receive.add_argument('--source', required=True)
    receive.add_argument('--submitted-at')
    receive.add_argument('--returned-at')
    review = commands.add_parser('review')
    review.add_argument('--job-id', required=True)
    review.add_argument('--status', choices=['accepted', 'rejected'], required=True)
    review.add_argument('--note', required=True)
    try:
        print(json.dumps(run(parser.parse_args()), ensure_ascii=False))
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
