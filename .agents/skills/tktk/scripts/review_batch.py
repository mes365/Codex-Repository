"""Persist actual model review notes, then claim ready work or export accepted selections."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import batch_queue as queue
import image_handoff as handoff
import deliver


def run(root, reviews, config_path=None, set_review_note=None):
    if not root.is_absolute():
        raise ValueError('task-dir must be absolute')
    root = root.resolve()
    if not isinstance(reviews, list) or not reviews:
        raise ValueError('Supply nonempty actual visual reviews; no automatic acceptance')
    identifiers = [handoff.job_id(r['job_id']) for r in reviews]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate review id')
    plan = queue.read(root/'.tktk/queue.json')
    table = queue.validate(plan, check_files=False)
    # Preflight every observed review before recording changes.
    for review in reviews:
        if review['job_id'] not in table or review['status'] not in ('accepted', 'rejected') or not review['note'].strip():
            raise ValueError('Each review needs a planned id, accepted/rejected and observed visual note')
        r = handoff.read_job(root, review['job_id'])
        image, _ = handoff.image_path(r['saved_image'])
        if not image.is_relative_to(root) or handoff.digest(image) != r['sha256']:
            raise ValueError('Review file changed or escapes task root')
    for review in reviews:
        r = handoff.read_job(root, review['job_id'])
        if r['status'] != review['status'] or r['review_note'] != review['note'].strip():
            handoff.run(SimpleNamespace(task_dir=str(root), command='review',
                job_id=review['job_id'], status=review['status'], note=review['note']))
    result = {'reviews_recorded': identifiers, 'batch': None, 'delivery': None}
    if any(r['status'] == 'rejected' for r in reviews):
        return result | {'action': 'Inspect rejected pages; no automatic refill or export'}
    if config_path:
        config = queue.read(Path(config_path))
        selected = [identifier for p in config['products'] for identifier in p['jobs']]
        if selected and all(queue.record(root, identifier)['status'] == 'accepted' for identifier in selected):
            if not set_review_note or not set_review_note.strip():
                return result | {'action': 'Selected images accepted; actual cross-page review note required before export'}
            handoff.atomic_json(root/'.tktk/set-review.json', {'note': set_review_note.strip(), 'reviewed_at': handoff.now()})
            timing = deliver.export(root, config)
            return result | {'action': 'delivered', 'delivery': {
                k: timing[k] for k in ('archive', 'delivery_ready_at', 'selected')}}
    result['batch'] = queue.run(SimpleNamespace(task_dir=str(root), command='claim',
        limit=3, auto_refill=True, pending_limit=plan.get('capacity', 2)*2))
    return result | {'action': 'dispatch_claimed_jobs' if result['batch']['jobs'] else 'review_or_reconcile_remaining'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-dir', required=True)
    parser.add_argument('--reviews-json', required=True)
    parser.add_argument('--delivery-config')
    parser.add_argument('--set-review-note')
    args = parser.parse_args()
    try:
        print(json.dumps(run(Path(args.task_dir), json.loads(args.reviews_json),
            args.delivery_config, args.set_review_note), ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
