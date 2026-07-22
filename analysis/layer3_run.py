#!/usr/bin/env python3
"""Layer-3 behavioural-preservation harness. For each repaired trajectory (iterative arms), materialise
its final_source into a corpus working copy, run the frozen 30-driver characterisation suite (--check),
and classify the repaired instance's behaviour:

  pass          — golden-master output unchanged (behaviour preserved) / smoke driver ran (OB)
  regression    — golden-master output differs (behavioural regression) / smoke driver threw
  contract      — the driver no longer compiles against the repaired public surface (God Class
                  extract-class API change; adjudicated, not a regression)

Also records any *collateral* regressions in OTHER instances' drivers. Emits one JSONL row per built final.
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

FILE_TO_KEY = {
    "CycleCountService.cs": ("Inventory.CycleCountService", "god_class"),
    "StockController.cs": ("Inventory.StockController", "god_class"),
    "AllocationCalculator.cs": ("AllocationCalculator.Allocate", "long_method"),
    "ReplenishmentPlanner.cs": ("ReplenishmentPlanner.BuildPlan", "long_method"),
    "SnapshotWriter.cs": ("SnapshotWriter.Write", "obsolete_api_usage"),
    "StockSync.cs": ("StockSync.Reconcile", "obsolete_api_usage"),
    "BillingManager.cs": ("Invoicing.BillingManager", "god_class"),
    "StatementBuilder.cs": ("Invoicing.StatementBuilder", "god_class"),
    "InvoiceRenderer.cs": ("InvoiceRenderer.Render", "long_method"),
    "VatResolver.cs": ("VatResolver.Resolve", "long_method"),
    "CurrencyConverter.cs": ("CurrencyConverter.Convert", "obsolete_api_usage"),
    "PdfExporter.cs": ("PdfExporter.Export", "obsolete_api_usage"),
    "NotificationCenter.cs": ("Notifications.NotificationCenter", "god_class"),
    "DispatchPipeline.cs": ("DispatchPipeline.Run", "long_method"),
    "RetryPolicy.cs": ("RetryPolicy.NextDelay", "long_method"),
    "EmailClient.cs": ("EmailClient.SendEmail", "obsolete_api_usage"),
    "PushClient.cs": ("PushClient.SendPush", "obsolete_api_usage"),
    "SmsClient.cs": ("SmsClient.SendSms", "obsolete_api_usage"),
    "OrderProcessor.cs": ("Ordering.OrderProcessor", "god_class"),
    "CheckoutCoordinator.cs": ("Ordering.CheckoutCoordinator", "god_class"),
    "ReturnsHandler.cs": ("Ordering.ReturnsHandler", "god_class"),
    "OrderImporter.cs": ("OrderImporter.ImportBatch", "long_method"),
    "PricingRules.cs": ("PricingRules.ApplyAdjustments", "long_method"),
    "LabelPrinter.cs": ("LabelPrinter.Print", "obsolete_api_usage"),
    "RecurrenceEngine.cs": ("Scheduling.RecurrenceEngine", "god_class"),
    "ScheduleManager.cs": ("Scheduling.ScheduleManager", "god_class"),
    "Scheduler.cs": ("Scheduler.PlaceJobs", "long_method"),
    "SlotFinder.cs": ("SlotFinder.FindFirstFit", "long_method"),
    "CalendarFeed.cs": ("CalendarFeed.Build", "obsolete_api_usage"),
    "ReminderSender.cs": ("ReminderSender.Send", "obsolete_api_usage"),
}
SKIP = {"bin", "obj", ".git", ".vs", ".idea"}
LINE = re.compile(r"^(PASS|REGRESSION|MISSING-GOLDEN)\s+(.+?)\s*$")


def copytree(src: Path, dst: Path):
    for f in src.rglob("*"):
        rel = f.relative_to(src)
        if any(p in SKIP for p in rel.parts):
            continue
        if f.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / rel)


def run_check(charproj: Path, golden: Path) -> tuple[dict, bool]:
    """Returns (per-key result dict, build_ok)."""
    p = subprocess.run(["dotnet", "run", "-c", "Release", "--project", str(charproj), "--", "--check", str(golden)],
                       capture_output=True, text=True, timeout=600)
    out = p.stdout + "\n" + p.stderr
    results = {}
    for ln in out.splitlines():
        m = LINE.match(ln.strip())
        if m:
            results[m.group(2)] = m.group(1)
    build_ok = bool(results) or "ALL PASS" in out
    if not build_ok and re.search(r":\s*error\s+CS", out):
        build_ok = False
    return results, (len(results) > 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trajectories", required=True, type=Path)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--corpus", required=True, type=Path, help="pristine corpus dir (has Corpus.sln)")
    ap.add_argument("--charproj", required=True, type=Path, help="frozen characterization project dir")
    ap.add_argument("--golden", required=True, type=Path, help="frozen golden dir")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--work", type=Path, default=Path(os.environ.get("TEMP", "/tmp")) / "hybridlens-l3-work")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    work = args.work
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    print(f"[l3] copying corpus -> {work}", flush=True)
    copytree(args.corpus, work)
    chardst = work / "src" / "Characterization"
    chardst.mkdir(parents=True, exist_ok=True)
    for f in args.charproj.glob("*"):
        if f.is_file():
            shutil.copy2(f, chardst / f.name)

    # Baseline sanity: the frozen oracle must pass on the pristine working copy.
    print("[l3] baseline sanity check (pristine)…", flush=True)
    base, ok = run_check(chardst, args.golden)
    nfail = sum(1 for v in base.values() if v != "PASS")
    print(f"[l3] baseline: {len(base)} drivers, {nfail} non-PASS", flush=True)
    if not base or nfail > 0:
        print("[l3] ABORT: frozen oracle does not pass on pristine — stale goldens?", file=sys.stderr)
        return 2

    trajs = sorted(args.trajectories.glob("*.json"))
    rows = []
    scored = 0
    for tf in trajs:
        try:
            d = json.loads(tf.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not d.get("build_passed_final") or not d.get("final_source"):
            continue
        rel = str(d.get("file", "")).replace("\\", "/")
        base_name = os.path.basename(rel)
        if base_name not in FILE_TO_KEY:
            continue
        key, typ = FILE_TO_KEY[base_name]
        if args.limit and scored >= args.limit:
            break

        target = work / rel
        pristine = args.corpus / rel
        original = pristine.read_text(encoding="utf-8-sig")
        try:
            target.write_text(d["final_source"], encoding="utf-8")
            results, ran = run_check(chardst, args.golden)
        finally:
            target.write_text(original, encoding="utf-8")

        if not ran:
            primary, collateral = "contract", []
        else:
            primary = {"PASS": "pass", "REGRESSION": "regression"}.get(results.get(key, "MISSING"), "missing")
            collateral = [k for k, v in results.items() if v == "REGRESSION" and k != key]
        scored += 1
        run_no = d.get("run")
        rows.append({"arm": args.arm, "anti_pattern": typ, "instance": key, "run": run_no,
                     "primary": primary, "collateral": collateral, "ran": ran})
        print(f"[l3] [{scored}] {args.arm} {typ:18} {key:32} run{run_no} -> {primary}"
              + (f"  COLLATERAL {collateral}" if collateral else ""), flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    print(f"[l3] done: {scored} states scored -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
