"""Protocol and CLI regression tests for the unified thesis entry point."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from analysis import run_experiment as runner


class ExperimentRunnerTests(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, str(runner.ROOT/'analysis/run_experiment.py'), *args],
                              cwd=tempfile.gettempdir(), capture_output=True, text=True)

    def test_dry_run_needs_no_sdk_credentials_or_external_corpus(self):
        with tempfile.TemporaryDirectory() as folder:
            out = str(Path(folder)/'not created')
            with patch.dict(os.environ, {'CORPUS': '/missing/corpus.sln', 'DOTNET': '/missing/dotnet'}, clear=False):
                result = self.call('--study','factorial','--out',out,'--dry-run')
            self.assertEqual(0,result.returncode,result.stderr)
            self.assertFalse(Path(out).exists())
            self.assertIn('factorial_test_feedback_analysis.py',result.stdout)
            self.assertIn('factorial_glmm.py',result.stdout)
            self.assertLess(result.stdout.index('[campaign]'),result.stdout.index('[oracle]'))
            self.assertLess(result.stdout.index('[oracle]'),result.stdout.index('[analyse]'))

    def test_stage_and_from_are_mutually_exclusive(self):
        result=self.call('--stage','tables','--from','figures','--dry-run')
        self.assertEqual(2,result.returncode)

    def test_invalid_stage_is_rejected_before_execution(self):
        result=self.call('--study','factorial','--stage','tables','--dry-run')
        self.assertEqual(2,result.returncode)

    def test_from_oracle_never_schedules_repair_calls(self):
        result=self.call('--study','factorial','--from','oracle','--dry-run')
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertNotIn('[campaign]',result.stdout)
        self.assertNotIn('[tests]',result.stdout)
        self.assertIn('[quality]',result.stdout)
        self.assertIn('[analyse]',result.stdout)

    def test_default_is_offline_thesis_reproduction(self):
        result=self.call('--dry-run')
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertNotIn('dotnet',result.stdout)
        self.assertNotIn('v04_run',result.stdout)
        self.assertIn('maintenance_figures.py',result.stdout)
        self.assertIn('combined_fix/render.py',result.stdout)

    def test_replication_preserves_recorded_route_temperature_and_paths(self):
        with patch.object(runner, 'execute') as execute:
            runner.main(['--study','replication','--dry-run','--','--packets','/path with spaces',
                         '--out','/destination','--provider','noop'])
        command=execute.call_args.args[0].command
        self.assertIn('/path with spaces',command)
        for flag, value in [('--model-key','claude-opus-5-5'),('--api','messages'),('--temperature','1')]:
            self.assertEqual(value,command[command.index(flag)+1])
        self.assertNotIn('live',command)

    def test_introduction_routes_run_subcommand(self):
        with patch.object(runner,'execute') as execute:
            runner.main(['--study','introduction','--stage','campaign','--','--help'])
        self.assertEqual(['run','--help'],execute.call_args.args[0].command[2:])

    def test_native_freeze_requires_write_freeze(self):
        result=self.call('--study','interventions','--stage','freeze','--dry-run','--','--packets','missing')
        self.assertEqual(2,result.returncode)
        self.assertIn('--write-freeze',result.stderr)

    def test_failed_command_propagates_without_running_later_stages(self):
        with patch.object(runner.subprocess,'run',side_effect=subprocess.CalledProcessError(7,['failed'])) as call:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(subprocess.CalledProcessError):
                runner.main(['--study','thesis','--out','/unused'])
        self.assertEqual(1,call.call_count)

    def test_incomplete_campaign_cannot_reach_private_oracle(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            manifest=base/'manifest.json'
            manifest.write_text(json.dumps({'assignments':[{'assignment_id':'a'},{'assignment_id':'b'}]}))
            (base/'execution-ledger.jsonl').write_text(json.dumps({'assignment_id':'a','completed':True})+'\n')
            with self.assertRaisesRegex(ValueError,'every frozen assignment'):
                runner.ensure_sealed(manifest,base)
            with (base/'execution-ledger.jsonl').open('a') as handle:
                handle.write(json.dumps({'assignment_id':'b','completed':False})+'\n')
            with self.assertRaises(ValueError):runner.ensure_sealed(manifest,base)
            with (base/'execution-ledger.jsonl').open('a') as handle:
                handle.write(json.dumps({'assignment_id':'b','completed':True})+'\n')
            runner.ensure_sealed(manifest,base)

    def test_industrial_no_restore_keeps_obj_and_uses_isolated_tree(self):
        steps=runner.repair_steps('context-industrial','test-output',{})
        oracle=next(s for s in steps if s.stage=='oracle')
        self.assertIn('-p:ProductRoot={WORKING_ROOT}',oracle.command)
        skipped=[oracle.command[i+1] for i,x in enumerate(oracle.command) if x=='--working-copy-skip']
        self.assertNotIn('obj',skipped)
        self.assertIn('--no-restore',oracle.command)


if __name__=='__main__':unittest.main()
