import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import messages_provider as mp

MESSAGES = [dict(role='system', content='SYS'), dict(role='user', content='hello'),
            dict(role='assistant', content='bad json'), dict(role='user', content='fix it')]
CONFIG = dict(Model='claude-opus-5-5', BaseUrl='https://res.openai.azure.com/', ApiKey='k', Temperature=1)


class RequestTests(unittest.TestCase):
    def test_system_message_is_lifted_out_and_turns_keep_their_order(self):
        system, turns = mp.split_messages(MESSAGES)
        self.assertEqual(system, 'SYS')
        self.assertEqual([t['role'] for t in turns], ['user', 'assistant', 'user'])

    def test_body_carries_the_recorded_temperature_only_when_set(self):
        self.assertEqual(mp.build_body(MESSAGES, 16384, CONFIG)['temperature'], 1)
        self.assertNotIn('temperature', mp.build_body(MESSAGES, 100, dict(CONFIG, Temperature=None)))
        self.assertEqual(mp.build_body(MESSAGES, 16384, CONFIG)['max_tokens'], 16384)

    def test_the_url_is_the_entry_own_host_never_another_vendor(self):
        self.assertEqual(mp.build_url(CONFIG), 'https://res.openai.azure.com/anthropic/v1/messages')
        with self.assertRaises(SystemExit):
            mp.build_url(dict(CONFIG, BaseUrl=None))
        with self.assertRaises(SystemExit):
            mp.build_url(dict(CONFIG, BaseUrl='https://api.anthropic.com'))

    def test_headers_carry_the_key_and_version(self):
        headers = mp.build_headers(CONFIG)
        self.assertEqual(headers['x-api-key'], 'k')
        self.assertIn('anthropic-version', headers)


class ResponseTests(unittest.TestCase):
    RAW = dict(model='claude-opus-5-5', stop_reason='end_turn',
               usage=dict(input_tokens=1200, output_tokens=340, cache_creation_input_tokens=0, cache_read_input_tokens=0),
               content=[dict(type='thinking', thinking='...'), dict(type='text', text='{"edits":'), dict(type='text', text='[]}')])

    def test_text_blocks_are_joined_and_thinking_is_ignored(self):
        text, call = mp.parse_response(self.RAW)
        self.assertEqual(text, '{"edits":[]}')
        self.assertEqual((call['input_tokens'], call['output_tokens']), (1200, 340))
        self.assertEqual(call['finish_reason'], 'end_turn')

    def test_cached_tokens_count_towards_the_ledger_value(self):
        raw = dict(self.RAW, usage=dict(input_tokens=10, output_tokens=5, cache_creation_input_tokens=3, cache_read_input_tokens=7))
        self.assertEqual(mp.ledger_tokens(mp.parse_response(raw)[1]), 25)

    def test_missing_usage_is_an_error_not_zero(self):
        with self.assertRaises(RuntimeError):
            mp.parse_response(dict(content=[dict(type='text', text='x')]))


class NormalisationTests(unittest.TestCase):
    JSON = '{"edits":[]}'
    FENCE = '`' * 3

    def fenced(self, body, tag='json'):
        return f'{self.FENCE}{tag}\n{body}\n{self.FENCE}'

    def test_pure_json_and_wholly_fenced_replies_are_unchanged(self):
        self.assertEqual(mp.normalise_reply(self.JSON), (self.JSON, False))
        reply = self.fenced(self.JSON)
        self.assertEqual(mp.normalise_reply(reply), (reply, False))

    def test_prose_around_a_single_fenced_block_is_dropped(self):
        reply = 'Extract the helpers.\n\nNote: removed a no-op.\n\n' + self.fenced(self.JSON) + '\n'
        self.assertEqual(mp.normalise_reply(reply), (self.JSON, True))
        self.assertEqual(mp.normalise_reply('Here:\n' + self.fenced(self.JSON, '')), (self.JSON, True))

    def test_prose_around_a_raw_json_edit_object_is_dropped(self):
        edit = '{"edits":[{"file":"a.cs","start_line":1,"end_line":2,"text":"x\\ny"}]}'
        self.assertEqual(mp.normalise_reply('The compile error came from an extra brace.\n\n' + edit), (edit, True))
        self.assertEqual(mp.normalise_reply(edit + '\n\nThat should compile now.'), (edit, True))

    def test_prose_with_a_broken_or_absent_edit_object_is_left_for_the_strict_parser(self):
        broken = 'See below.\n{"edits":[{"file":'
        self.assertEqual(mp.normalise_reply(broken), (broken, False))
        self.assertEqual(mp.normalise_reply('The object {"other": 1} is not an edit.'), ('The object {"other": 1} is not an edit.', False))

    def test_ambiguous_or_missing_blocks_are_left_for_the_strict_parser(self):
        two = 'a\n' + self.fenced('{"edits":[1]}') + '\nb\n' + self.fenced('{"edits":[2]}')
        self.assertEqual(mp.normalise_reply(two), (two, False))
        self.assertEqual(mp.normalise_reply('no json here'), ('no json here', False))


class ReservationTests(unittest.TestCase):
    def test_the_reservation_is_widened_for_the_different_tokeniser(self):
        self.assertEqual(mp.RESERVATION_SCALE, 1.25)


if __name__ == '__main__':
    unittest.main()
