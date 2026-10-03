"""Portable bootstrap for a pinned parser package directory."""
import argparse,json,sys
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--packages',type=Path,required=True);ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--scope',type=Path,required=True);ap.add_argument('--language',required=True);ap.add_argument('--repository',required=True);ap.add_argument('--commit',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
sys.path.insert(0,str(a.packages.resolve()))
from syntax_probe import run,canonical
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ingest'))
from validate import validate
result=run(a.archive,a.language,a.repository,a.commit,json.loads(a.scope.read_text()));validate(result);a.output.write_bytes(canonical(result))
