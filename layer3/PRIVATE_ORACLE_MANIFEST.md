# Private Layer-3 Oracle Manifest

Status: frozen  
Manifest version: 1.0.0  
Baseline date: 2026-07-27  
Corpus: `Z:\GitHub\hybrid-pipeline-corpus\corpus`

## Baseline result

The existing Layer-3 harness was copied into a temporary pristine corpus
working tree and executed in `--check` mode against the golden directory.

- Drivers discovered: 30
- Passing: 30
- Non-passing: 0
- Result: `ALL PASS`

The corpus was not modified. The working copy was temporary.

The user confirmed on 2026-07-27 that the exact working-tree files hashed below
are the canonical private oracle. The existing
`InvoiceRenderer.Render.golden` difference relative to Git is line-ending-only;
the frozen hash below intentionally identifies the confirmed CRLF version.

## SHA-256

```text
6914d568805bd654b8ecd185f94479f9aa838bdffb380cab1edba4b71d1782e9  layer3/characterization/Drivers.Inventory.cs
7e5e20c9d9b9172f5486a783d7c7c85942e17dd9c280d9cd521c32f4e9d941fb  layer3/characterization/Drivers.Invoicing.cs
088347635b71a902b08333bae239789547c8f9fda326b6d0b9dbd30e68062ec3  layer3/characterization/Drivers.Notifications.cs
f020a97ceec5fa996031a9b96cd9e06fd26129c4a8aac1330a34347871733fc7  layer3/characterization/Drivers.Ordering.cs
90b9195499891fd7176ade6a60a4c3616a75b539c7fe7130148ca1daae92e762  layer3/characterization/Drivers.Scheduling.cs
ea6127300f9606d24ca49df0985806639dd761aac514f63f690105daa7921334  layer3/characterization/Program.cs
f71034d63698f541f3f0560423e800cc45353a3ef9e658059c96a417460132e2  layer3/characterization/Characterization.csproj
567c7e75263e28c4785fdd7011ebe72d33bb560378fd5da251982e11b830bc0c  layer3/golden/AllocationCalculator.Allocate.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/CalendarFeed.Build.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/CurrencyConverter.Convert.golden
8db14bd8d5f89f9694899ba4d74f6c491fd7cbd21e64f578b78428735f3ea172  layer3/golden/DispatchPipeline.Run.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/EmailClient.SendEmail.golden
701ef707da8cf7f5fbc7a2e932e3aa48ad658c37cdbd67b79fb8354fcf0b024e  layer3/golden/Inventory.CycleCountService.golden
32696dadca2c26c88b064d2d20d2eb357f031d142f40cb55b6c17d5d30e96eff  layer3/golden/Inventory.StockController.golden
147c1547e2adf47f359cf2b2a66dd8b813075dd61d7607a640c797de97902da0  layer3/golden/InvoiceRenderer.Render.golden
66c761e24c2742ae9e349fcbc1aa5a604a333f9ce13b8900f34ec65979eff123  layer3/golden/Invoicing.BillingManager.golden
387dcbd7b100756ba7eb4125badc837e87c7d2c4d8f39f2c60911aa81dc9f1f4  layer3/golden/Invoicing.StatementBuilder.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/LabelPrinter.Print.golden
91b15984f036e49416e492b7e1ff1ed81cce0b461cbcb2974661e5eca9fcebfd  layer3/golden/Notifications.NotificationCenter.golden
472708c71f35e5c1cb70e5753173c14686e68d1f85f1304f56bbfe370928aa7a  layer3/golden/OrderImporter.ImportBatch.golden
becbdbd0dbf4e3025952e34bf8d26faeca92cbdd12d21d0e36f2d12d0f599d68  layer3/golden/Ordering.CheckoutCoordinator.golden
427e3bc921f758d39c7a40155580f1234eae9ae8d60a2354ea7f2c495eb21c60  layer3/golden/Ordering.OrderProcessor.golden
44840d2b6531b26a4d7c1e2ce568d21d52649b3650bfabfe76d3cbdd4a9b04b1  layer3/golden/Ordering.ReturnsHandler.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/PdfExporter.Export.golden
75398069adcf7e81288afc0edd0a2d859d7443c1d0c6b5ebe3e4e35ed4771c25  layer3/golden/PricingRules.ApplyAdjustments.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/PushClient.SendPush.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/ReminderSender.Send.golden
93bf84b32cf42e9ca447ce28144300d6c64c56400c22ac08f6c1f445e12417d4  layer3/golden/ReplenishmentPlanner.BuildPlan.golden
3db0acaff1154fddf71fec900c08d8d6947ef4a466a8291aeef3e7a4120af389  layer3/golden/RetryPolicy.NextDelay.golden
4719896ab918afe1b7efb118b9980d7d9ab05ffdd512353fad34eb9167e3b1ab  layer3/golden/Scheduler.PlaceJobs.golden
792eba39860a5a587706b70b27cd8bab84a5e23db855750d94c9460eb4974ca7  layer3/golden/Scheduling.RecurrenceEngine.golden
f774401d703235f29157ee47eb8babbbff73d1934edf4ae67004923ac857f7b2  layer3/golden/Scheduling.ScheduleManager.golden
c1d9587fc04426ef92ff69fb7847c398ad6dae86bc2667814b8542905a3f1a98  layer3/golden/SlotFinder.FindFirstFit.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/SmsClient.SendSms.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/SnapshotWriter.Write.golden
f18916ed667cb59bceda794f8999a0fb5108a8fc9dffa9123cb98fac15c3f1d8  layer3/golden/StockSync.Reconcile.golden
6e865a3c8b1e531dee06ee4da74413e5b89c1597344dddb7b73594db5b5be090  layer3/golden/VatResolver.Resolve.golden
```

## Freeze completion checklist

- [x] Confirm the current working-tree oracle is the intended canonical version.
- [ ] Record the pipeline Git revision.
- [ ] Record the corpus Git revision or immutable release tag.
- [ ] Recompute hashes after any intentional oracle edit.
- [ ] Rerun the pristine baseline after any intentional oracle edit.
- [x] Change status to `frozen`.
