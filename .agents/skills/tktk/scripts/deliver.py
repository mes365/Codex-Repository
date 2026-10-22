"""Export reviewed tktk jobs and supplied copy once; no generation or image editing."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

from batch_queue import audit, read
from image_handoff import atomic_json, digest, image_path, job_id, now, timestamp


def inside(root, name):
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Output escapes task directory')
    return target


def export(root, config):
    begin = now()
    plan = read(root / '.tktk/queue.json')
    table = {j['id']: j for j in plan['jobs']}
    products = config['products']
    if not products or len({p['id'] for p in products}) != len(products):
        raise ValueError('Nonempty, distinct products required')
    prepared, selected_ids, output_names = [], set(), set()
    # Validate every product before writing delivery files. Never auto-accept images.
    for product in products:
        identifier = job_id(product['id'])
        name = product['name']
        if not name.isascii() or not 0 < len(name) <= 30:
            raise ValueError('Product name must be ASCII, 1..30 characters including spaces')
        for key in ('title', 'caption', 'music', 'brief', 'visual_notes'):
            if not product.get(key, '').strip():
                raise ValueError(f'Missing supplied copy: {key}')
        if not product.get('tags') or any(not isinstance(t, str) or not t.strip() for t in product['tags']):
            raise ValueError('Supply relevant tags; do not invent trend evidence')
        if len(product['jobs']) != product.get('expected_pages', 5):
            raise ValueError('Selected pages differ from requested count')
        pages = []
        for index, jid in enumerate(product['jobs'], 1):
            job_id(jid)
            if jid in selected_ids or jid not in table:
                raise ValueError('Duplicate or unknown selection')
            selected_ids.add(jid)
            j = table[jid]
            if str(j['product']) != identifier or int(j['page']) != index:
                raise ValueError('Selection product/page does not match plan')
            r = read(root / f'.tktk/jobs/{jid}.json')
            if r['status'] != 'accepted' or not r.get('review_note', '').strip():
                raise ValueError('All selected pages require actual visual review')
            path, extension = image_path(r['saved_image'])
            if not path.is_relative_to(root) or digest(path) != r['sha256']:
                raise ValueError('Selected result changed or escapes task directory')
            target = inside(root, f'{identifier}/{index:02}{extension}')
            if target.exists() and digest(target) != r['sha256']:
                raise ValueError('Existing selected output differs; preserve it before replacing')
            dispatch = root / f'.tktk/dispatch/{jid}.json'
            actual = read(dispatch) if dispatch.exists() else j
            hook = j.get('hook', '')
            if not hook:
                match = re.search(r'Overlay EXACTLY:?\s+"([^"]+)"', actual.get('prompt', ''))
                hook = match.group(1).replace('\\n', '\n') if match else 'See image / overlay not recorded'
            pages.append({'page': index, 'job_id': jid, 'file': target.name,
                          'source_image': str(path), 'target': target, 'sha256': r['sha256'],
                          'hook': hook, 'review': r['review_note'], 'record': r,
                          'prompt_record': actual,
                          'prompt_source': 'dispatch snapshot' if dispatch.exists() else 'plan fallback; historical submission not independently confirmed'})
            output_names.add(f'{identifier}/{target.name}')
        prepared.append((product, identifier, pages))
    if not config.get('research', '').strip():
        raise ValueError('Supply sources and truthful limits for tags/music')
    files, statuses = [], []
    overview = ['# Publish copy', '']
    for product, identifier, pages in prepared:
        folder = inside(root, identifier)
        folder.mkdir(parents=True, exist_ok=True)
        for p in pages:
            if not p['target'].exists():
                shutil.copyfile(p['source_image'], p['target'])
            if digest(p['target']) != p['sha256']:
                raise ValueError('Selected copy hash mismatch')
            files.append((p['target'], f"{identifier}/{p['file']}"))
        tags = ' '.join('#' + t.lstrip('#') for t in product['tags'])
        content = [f"# {product['title']}", '', f"Title: {product['title']}", '',
                   f"Product name: {product['name']} ({len(product['name'])} characters)", '',
                   f"Caption: {product['caption']}", '', tags, '', product['brief'], '',
                   product['visual_notes'], '', '| Page | Hook | Actual review |', '| --- | --- | --- |']
        for p in pages:
            values = [str(p['page']), p['hook'], p['review']]
            content.append('| ' + ' | '.join(v.replace('\n', ' ').replace('|', '\\|') for v in values) + ' |')
        content += ['', 'Music: ' + product['music'], '',
                    'Sources and verification limits: ../research.md', '',
                    'AI-generated scene; not a customer testimonial. Conversion has not been tested.']
        (folder/'publish-copy.md').write_text('\n'.join(content), encoding='utf-8')
        clean_pages = [{k: v for k, v in p.items() if k not in ('target', 'record', 'prompt_record')}
                       for p in pages]
        status = {'product': identifier, 'complete': True, 'selected': len(pages), 'pages': clean_pages}
        atomic_json(folder/'status.json', status)
        atomic_json(folder/'prompts.json', [p['prompt_record'] for p in pages])
        atomic_json(folder/'timings.json', [p['record'] for p in pages])
        for name in ('publish-copy.md', 'status.json', 'prompts.json', 'timings.json'):
            files.append((folder/name, f'{identifier}/{name}'))
        statuses.append({'product': identifier, 'selected': len(pages), 'complete': True})
        overview += [f"## {identifier} · {product['name']}", f"Title: {product['title']}",
                     f"Product name: {product['name']} ({len(product['name'])} characters)",
                     f"Caption: {product['caption']}", tags, f"Details: {identifier}/publish-copy.md", '']
    (root/'all-publish-copy.md').write_text('\n\n'.join(overview), encoding='utf-8')
    (root/'research.md').write_text(config['research'], encoding='utf-8')
    atomic_json(root/'batch-status.json', statuses)
    records = [read(path) for path in sorted((root/'.tktk/jobs').glob('*.json'))]
    timing = {'agent_started_at': config.get('agent_started_at'),
              'request_received_at': config.get('request_received_at'),
              'final_reply_sent_at': None, 'user_reported_seconds': config.get('user_reported_seconds'),
              'packaging_started_at': begin, 'selected': len(selected_ids), 'call_records': len(records),
              'last_image_returned_at': max((r['returned_at'] for r in records if r.get('returned_at')), default=None),
              'note': 'Unknown host/message timestamps stay null. File-ready time is written to delivery-timing.json after ZIP verification; final reply time is not observed here.'}
    start = config.get('agent_started_at')
    if start:
        timestamp(start)
        timing['call_audit_before_packaging'] = audit(root, start, begin)
    atomic_json(root/'task-timing.json', timing)
    atomic_json(root/'all-job-timings.json', records)
    for name in ('all-publish-copy.md', 'research.md', 'batch-status.json', 'task-timing.json', 'all-job-timings.json'):
        files.append((root/name, name))
    archive = inside(root, 'deliverable.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, name in files:
            z.write(path, name)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP integrity error')
        if not output_names.issubset(z.namelist()):
            raise ValueError('ZIP missing selected images')
        for path, name in files:
            if hashlib.sha256(z.read(name)).hexdigest() != digest(path):
                raise ValueError('ZIP differs from selected delivery files')
    timing.update(delivery_ready_at=now(), archive=str(archive))
    atomic_json(root/'delivery-timing.json', timing)
    return timing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-dir', required=True)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    try:
        if not Path(args.task_dir).is_absolute():
            raise ValueError('task-dir must be absolute')
        print(json.dumps(export(Path(args.task_dir).resolve(), read(Path(args.config))), ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
