"""Durable dispatch queue and timing audit for built-in image tools; no generation API."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import statistics
import sys
import uuid

from image_handoff import atomic_json, digest, image_path, job_id, now, timestamp


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def clock(value):
    timestamp(value)
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


@contextmanager
def guard(root):
    lock = root / '.tktk/queue.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(now())
    try:
        yield
    finally:
        lock.unlink()


def validate(plan, check_files=True):
    jobs = plan['jobs']
    if not jobs or plan.get('capacity', 2) not in (1, 2, 3):
        raise ValueError('Nonempty jobs and capacity 1, 2 or 3 required')
    table = {job_id(j['id']): j for j in jobs}
    if len(table) != len(jobs):
        raise ValueError('Duplicate job id')
    for j in jobs:
        if not j['prompt'].strip() or not j['product'] or int(j['page']) < 1:
            raise ValueError('Every job needs product, positive page and exact prompt')
        if check_files:
            image_path(j['product_image'])
        for dep in j.get('depends_on', []) + j.get('anchor_jobs', []):
            if dep not in table or dep == j['id']:
                raise ValueError('Unknown or self dependency')
            if table[dep]['product'] != j['product'] and not j.get('cross_product_gate_reason', '').strip():
                raise ValueError('Independent products must not wait for another full set; a real cross-product dependency needs cross_product_gate_reason')
        for dep in j.get('anchor_jobs', []):
            if table[dep]['product'] != j['product']:
                raise ValueError('Identity anchors cannot cross products')
    visiting, done = set(), set()

    def visit(identifier):
        if identifier in visiting:
            raise ValueError('Cyclic dependency')
        if identifier in done:
            return
        visiting.add(identifier)
        j = table[identifier]
        for dep in j.get('depends_on', []) + j.get('anchor_jobs', []):
            visit(dep)
        visiting.remove(identifier)
        done.add(identifier)
    for identifier in table:
        visit(identifier)
    return table


def record(root, identifier):
    identifier = job_id(identifier)
    path = root / f'.tktk/jobs/{identifier}.json'
    if path.exists():
        return read(path)
    path = root / f'.tktk/dispatch/{identifier}.json'
    return read(path) if path.exists() else {'status': 'planned'}


def references(root, j):
    original, _ = image_path(j['product_image'])
    paths = [str(original)]
    for identifier in j.get('anchor_jobs', []):
        r = record(root, identifier)
        if r['status'] != 'accepted':
            raise ValueError('Anchor has not passed visual review')
        path, _ = image_path(r['saved_image'])
        if not path.is_relative_to(root) or digest(path) != r['sha256']:
            raise ValueError('Anchor changed or escapes task directory')
        if str(path) not in paths:
            paths.append(str(path))
    return paths


def snapshot(root, plan, limit):
    if plan.get('capacity', 2) not in (1, 2, 3):
        raise ValueError('capacity must be 1, 2 or 3')
    table = {job_id(j['id']): j for j in plan['jobs']}
    states = {identifier: record(root, identifier) for identifier in table}
    active = [k for k, v in states.items() if v['status'] == 'dispatched']
    pending = [k for k, v in states.items() if v['status'] == 'generated_pending_review']
    slots = max(0, plan.get('capacity', 2) - len(active))
    ready, blocked, input_errors = [], [], []
    for identifier, j in table.items():
        if states[identifier]['status'] != 'planned':
            continue
        unmet = [dep for dep in j.get('depends_on', []) + j.get('anchor_jobs', [])
                 if states[dep]['status'] != 'accepted']
        if unmet:
            blocked.append({'id': identifier, 'waiting_for': unmet})
        else:
            try:
                paths = references(root, j)
                ready.append({'id': identifier, 'product': j['product'], 'page': j['page'],
                              'prompt': j['prompt'], 'referenced_image_paths': paths})
            except (OSError, ValueError, KeyError) as error:
                input_errors.append({'id': identifier, 'error': str(error)})
    return {'checked_at': now(), 'capacity': plan.get('capacity', 2), 'free_slots': slots,
            'dispatched_unreceived': active, 'pending_review': pending,
            'accepted': sum(r['status'] == 'accepted' for r in states.values()),
            'ready_count': len(ready), 'next': ready[:min(slots, limit)],
            'blocked': blocked, 'input_errors': input_errors,
            'action': 'dispatch_ready' if slots and ready else 'review' if pending
                      else 'wait_or_reconcile_dispatch' if active else 'inspect_remaining'}


def audit(root, started, ended):
    start, end = clock(started), clock(ended)
    if end < start:
        raise ValueError('End precedes start')
    paths = list(root.glob('.tktk/jobs/*.json')) + list(root.glob('*/.tktk/jobs/*.json'))
    rows = [read(p) for p in paths]
    valid, unknown = [], []
    for r in rows:
        if not r.get('submitted_at') or not r.get('returned_at'):
            unknown.append(r['job_id'])
            continue
        a, b = clock(r['submitted_at']), clock(r['returned_at'])
        if b < a or a < start or b > end:
            raise ValueError('Call interval outside requested audit window or reversed')
        valid.append((a, b))
    merged = []
    for a, b in sorted(valid):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(b, merged[-1][1])
        else:
            merged.append([a, b])
    gaps, cursor = [], start
    for a, b in merged:
        if a > cursor:
            gaps.append({'start': cursor.isoformat(), 'end': a.isoformat(),
                         'seconds': (a-cursor).total_seconds()})
        cursor = max(cursor, b)
    if end > cursor:
        gaps.append({'start': cursor.isoformat(), 'end': end.isoformat(),
                     'seconds': (end-cursor).total_seconds()})
    busy = sum((b-a).total_seconds() for a, b in merged)
    durations = [(b-a).total_seconds() for a, b in valid]
    events = [(a, 1) for a, b in valid if b > a] + [(b, -1) for a, b in valid if b > a]
    active = peak = 0
    for _, change in sorted(events, key=lambda x: (x[0], x[1])):
        active += change
        peak = max(peak, active)
    return {'records': len(rows), 'complete_intervals': len(valid), 'unknown_times': unknown,
            'total_seconds': (end-start).total_seconds(), 'request_union_seconds': busy,
            'no_request_seconds': (end-start).total_seconds()-busy if not unknown else None,
            'median_call_seconds': statistics.median(durations) if durations else None,
            'call_seconds_sum': sum(durations), 'observed_peak_inflight': peak,
            'observed_overlap_seconds': sum(durations)-busy,
            'concurrency_scope': 'Client tool-call interval overlap, not proof of GPU parallelism; incomplete records give only observed coverage.',
            'longest_gaps': sorted(gaps, key=lambda x: x['seconds'], reverse=True)[:5],
            'scope': 'Intervals cover tool waiting, not GPU time. Gaps include preparation, '
                     'visual review, context processing and dispatch delays; not all are avoidable. '
                     'Unknown call times make gaps provisional.'}


def reserve(root, jobs):
    batch_id = uuid.uuid4().hex
    stamp = now()
    written = []
    try:
        for j in jobs:
            destination = root / f".tktk/dispatch/{j['id']}.json"
            if destination.exists():
                raise ValueError('Dispatch already exists; reconcile it instead of resubmitting')
            atomic_json(destination, dict(j, job_id=j['id'], status='dispatched',
                                         batch_id=batch_id, dispatch_recorded_at=stamp))
            written.append(destination)
    except Exception:
        for path in written:
            path.unlink()
        raise
    return {'batch_id': batch_id, 'dispatch_recorded_at': stamp, 'task_dir': str(root),
            'python_executable': sys.executable,
            'handoff_script': str(Path(__file__).with_name('image_handoff.py').resolve()),
            'queue_script': str(Path(__file__).resolve()), 'jobs': jobs,
            'note': 'Launch all returned image calls before awaiting any receipt or other tool. Dispatch time is not actual submission time.'}


def run(args):
    if not Path(args.task_dir).is_absolute():
        raise ValueError('task-dir must be absolute')
    root = Path(args.task_dir).resolve()
    if args.command == 'audit':
        return audit(root, args.started_at, args.ended_at)
    (root / '.tktk/dispatch').mkdir(parents=True, exist_ok=True)
    plan_path = root / '.tktk/queue.json'
    with guard(root):
        if args.command == 'init':
            plan = read(Path(args.plan))
            validate(plan)
            if plan_path.exists():
                raise ValueError('Queue exists; resume with next, do not reset it')
            plan['queue_created_at'] = now()
            atomic_json(plan_path, plan)
            return {'initialized': True, 'jobs': len(plan['jobs'])}
        plan = read(plan_path)
        validate(plan, check_files=False)
        if args.command == 'next':
            if args.limit < 1:
                raise ValueError('limit must be positive')
            return snapshot(root, plan, args.limit)
        if args.command == 'claim':
            if args.limit < 1:
                raise ValueError('limit must be positive')
            snap = snapshot(root, plan, args.limit)
            auto = getattr(args, 'auto_refill', False)
            budget = getattr(args, 'pending_limit', None) or plan.get('capacity', 2) * 2
            if auto and (not isinstance(budget, int) or budget < plan.get('capacity', 2) or budget > 6):
                raise ValueError('pending-limit must be between capacity and 6')
            jobs = snap['next']
            if auto:
                available = max(0, budget - len(snap['pending_review']) - len(snap['dispatched_unreceived']))
                jobs = jobs[:available]
            return reserve(root, jobs) | {'free_slots_before': snap['free_slots'],
                'pending_review': snap['pending_review'], 'auto_refill': auto,
                'pending_limit': budget if auto else None}
        identifier = job_id(args.job_id)
        if identifier not in {j['id'] for j in plan['jobs']}:
            raise ValueError('Unknown queue job')
        destination = root / f'.tktk/dispatch/{identifier}.json'
        if args.command == 'submit':
            snap = snapshot(root, plan, len(plan['jobs']))
            j = next((j for j in snap['next'] if j['id'] == identifier), None)
            if j is None:
                raise ValueError('Job not ready, already dispatched, or capacity full')
            batch = reserve(root, [j])
            return j | {'dispatch_recorded_at': batch['dispatch_recorded_at'],
                        'note': 'Call built-in image tool now; record actual call times in receive.'}
        if record(root, identifier)['status'] != 'dispatched' or not args.note.strip():
            raise ValueError('fail requires an unreceived dispatch and observed error note')
        r = read(destination)
        r.update(status='failed', failed_at=now(), error=args.note.strip())
        atomic_json(destination, r)
        return r


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-dir', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init'); init.add_argument('--plan', required=True)
    nex = commands.add_parser('next'); nex.add_argument('--limit', type=int, default=1)
    claim = commands.add_parser('claim'); claim.add_argument('--limit', type=int, default=2)
    claim.add_argument('--auto-refill', action='store_true')
    claim.add_argument('--pending-limit', type=int)
    submit = commands.add_parser('submit'); submit.add_argument('--job-id', required=True)
    fail = commands.add_parser('fail'); fail.add_argument('--job-id', required=True); fail.add_argument('--note', required=True)
    aud = commands.add_parser('audit'); aud.add_argument('--started-at', required=True); aud.add_argument('--ended-at', required=True)
    try:
        print(json.dumps(run(parser.parse_args()), ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
