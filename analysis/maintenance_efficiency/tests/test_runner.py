import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]))
import run_pilot

class RunnerTests(unittest.TestCase):
    def test_prompt_reserve_covers_utf8_and_framing(self):
        messages=[{'role':'user','content':'α'*100}]
        self.assertEqual(run_pilot.prompt_reserve(messages),len(json.dumps(messages,ensure_ascii=False).encode())+512)
    def test_full_source_and_fences(self):
        self.assertEqual(run_pilot.extract_source('```csharp\nclass C {}\n```'),'class C {}\n')
        self.assertEqual(run_pilot.extract_source('class C {}'),'class C {}\n')
        with self.assertRaises(ValueError):run_pilot.extract_source('```csharp\nclass C {}')
    def test_explicit_output_cap_and_no_network_in_test(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'{"usage":{"prompt_tokens":10,"completion_tokens":2},"choices":[]}'
        with patch.object(run_pilot.urllib.request,'urlopen',return_value=Response()) as mocked:
            raw,_,body=run_pilot.provider_call([{'role':'user','content':'fixture'}],123,dict(BaseUrl='https://example.invalid',Model='fixture-model',ApiKey='fixture-not-a-secret'))
        self.assertEqual(body['max_completion_tokens'],123)
        self.assertNotIn('max_tokens',body)
        self.assertEqual(mocked.call_count,1)
        self.assertEqual(raw['usage']['prompt_tokens'],10)
    def test_no_automatic_retry_after_provider_error(self):
        with patch.object(run_pilot.urllib.request,'urlopen',side_effect=TimeoutError) as mocked:
            with self.assertRaises(TimeoutError):run_pilot.provider_call([],1,dict(BaseUrl='https://example.invalid',Model='fixture',ApiKey='fixture'))
        self.assertEqual(mocked.call_count,1)

if __name__=='__main__':unittest.main()
