"""Anthropic-compatible Messages route on the same Azure resource as the other deployments (protocol v0.6), with ledger reservation before
each call and reconciliation after it. The key is sent only to the host of the model entry's own BaseUrl, never to another vendor.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import replay_core as core
import replay_ledger as ledger
import replay_rate as rate

API_VERSION = '2023-06-01'
TIMEOUT_SECONDS = 600
# The token estimate is calibrated on another tokeniser: this model reported about 10% more input tokens than the estimate.
RESERVATION_SCALE = 1.25
FENCE = re.compile(r'```[A-Za-z]*[ \t]*\n(.*?)\n[ \t]*```', re.DOTALL)


def split_messages(messages):
    system = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
    return system, [dict(role=m['role'], content=m['content']) for m in messages if m['role'] != 'system']


def build_body(messages, max_tokens, config):
    system, turns = split_messages(messages)
    body = dict(model=config['Model'], max_tokens=max_tokens, system=system, messages=turns)
    if config.get('Temperature') is not None:
        body['temperature'] = config['Temperature']
    return body


def build_url(config):
    host = urllib.parse.urlparse(config.get('BaseUrl') or '').hostname or ''
    if not host.endswith('.azure.com'):
        raise SystemExit('The Messages route is used only with the Azure resource of the model entry (BaseUrl on azure.com)')
    return config['BaseUrl'].rstrip('/') + '/anthropic/v1/messages'


def build_headers(config):
    return {'content-type': 'application/json', 'x-api-key': config['ApiKey'], 'anthropic-version': API_VERSION}


def parse_response(raw):
    usage = raw.get('usage') or {}
    if usage.get('input_tokens') is None or usage.get('output_tokens') is None:
        raise RuntimeError('Provider omitted usage: campaign halted for reconciliation')
    text = ''.join(block.get('text', '') for block in raw.get('content', []) if block.get('type') == 'text')
    return text, dict(input_tokens=usage['input_tokens'], output_tokens=usage['output_tokens'],
                      cached_input_tokens=(usage.get('cache_read_input_tokens') or 0) + (usage.get('cache_creation_input_tokens') or 0),
                      reasoning_output_tokens=(usage.get('output_tokens_details') or {}).get('thinking_tokens'),
                      returned_model=raw.get('model'), finish_reason=raw.get('stop_reason'))


def normalise_reply(text):
    """Drop prose around a single fenced block, or around one raw JSON edit object.
    Pure JSON, a wholly fenced reply, and ambiguous or broken replies are left for the strict parser."""
    stripped = text.strip()
    if stripped.startswith('`' * 3):
        return text, False
    try:
        json.loads(stripped)
        return text, False
    except ValueError:
        pass
    blocks = FENCE.findall(text)
    if blocks:
        return (blocks[0].strip(), True) if len(blocks) == 1 else (text, False)
    start = text.find('{"edits"')
    if start < 0:
        return text, False
    try:
        edit, end = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return text, False
    return (text[start:start + end], True) if isinstance(edit, dict) else (text, False)


def ledger_tokens(call):
    return call['input_tokens'] + call['output_tokens'] + (call.get('cached_input_tokens') or 0)


def post(messages, max_tokens, config):
    request = urllib.request.Request(build_url(config), data=json.dumps(build_body(messages, max_tokens, config)).encode('utf-8'),
                                     headers=build_headers(config), method='POST')
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        raw = json.loads(response.read())
    return raw, time.monotonic() - started


def live_provider(config, ledger_path, experiment, max_output, tokens_per_minute=None):
    """Same signature as the chat-completions provider: provide(messages, current_text, reference_text, path, record) -> (text, call)."""
    history = []

    def provide(messages, current_text, reference_text, path, record=None):
        reserve = int(core.reservation(messages) * RESERVATION_SCALE) + max_output

        def send():
            if tokens_per_minute:
                pause = rate.wait_needed(history, time.monotonic(), reserve, tokens_per_minute)
                if pause:
                    time.sleep(pause)
            ledger.reserve(ledger_path, experiment, reserve)
            history.append((time.monotonic(), reserve))
            Path(f'{record}-intent.json').write_text(json.dumps(dict(status='sending', reserved_total_tokens=reserve)), encoding='utf-8')
            return post(messages, max_output, config)

        raw, elapsed = rate.with_rate_limit_retry(send, release=lambda: ledger.reconcile(ledger_path, experiment, reserved=reserve, used=0),
                                                  sleep=time.sleep, attempts=3)
        Path(f'{record}-raw-response.json').write_text(json.dumps(raw, indent=1), encoding='utf-8')
        text, call = parse_response(raw)
        text, call['format_normalised'] = normalise_reply(text)
        ledger.reconcile(ledger_path, experiment, reserved=reserve, used=ledger_tokens(call))
        return text, dict(call_id=Path(str(record)).name, model=config['Model'], outcome='completed', elapsed_seconds=elapsed, **call)
    return provide
