"""Shared cumulative token ledger: reserve before every provider call, reconcile to reported usage after it."""
import json
from pathlib import Path


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _save(path, state):
    tmp = Path(path).with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=1) + '\n', encoding='utf-8')
    tmp.replace(path)


def _entry(state, experiment):
    return next(e for e in state['entries'] if e['experiment'] == experiment)


def _refresh(state):
    reserved = sum(e.get('reserved_tokens', 0) for e in state['entries'])
    state['remaining'] = state['authorised_ceiling'] - state['cumulative_recorded_tokens']
    state['available_unreserved'] = state['remaining'] - reserved


def open_entry(path, experiment, output):
    state = _load(path)
    if any(e['status'] != 'completed' or e.get('reserved_tokens', 0) for e in state['entries']):
        raise ValueError('Unreconciled ledger entry: resolve it before opening a new campaign')
    state['entries'].append(dict(experiment=experiment, status='running', recorded_tokens=0, reserved_tokens=0, output=str(output)))
    _refresh(state)
    _save(path, state)


def reserve(path, experiment, amount):
    state = _load(path)
    _refresh(state)
    if amount > state['available_unreserved']:
        raise ValueError(f'Reservation of {amount} exceeds the available {state["available_unreserved"]} tokens')
    _entry(state, experiment)['reserved_tokens'] += amount
    _refresh(state)
    _save(path, state)


def reconcile(path, experiment, reserved, used):
    state = _load(path)
    entry = _entry(state, experiment)
    entry['reserved_tokens'] -= reserved
    entry['recorded_tokens'] += used
    state['cumulative_recorded_tokens'] += used
    _refresh(state)
    _save(path, state)
    if used > reserved:
        raise ValueError(f'Provider usage {used} exceeded the reservation {reserved}')


def close_entry(path, experiment):
    state = _load(path)
    entry = _entry(state, experiment)
    if entry['reserved_tokens']:
        raise ValueError('Cannot close an entry with outstanding reservations')
    entry['status'] = 'completed'
    _refresh(state)
    _save(path, state)
