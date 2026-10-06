"""Materialise versioned development tasks, hand references, mutants and source-based tests.
No model calls. Task choices are purposive instrument development, not random population sampling.
"""
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
EVIDENCE=ROOT.parents[1]/'repair_design_quality/generated'
PAIR_MANIFEST=ROOT.parent/'generated/campaign.json'


def apply(source,edits):
    for old,new,expected in edits:
        if source.count(old)!=expected:raise ValueError('Reference edit does not match frozen baseline')
        source=source.replace(old,new)
    return source

HEADER='''using System.Text.Json;
public static class MaintenanceTests {
 static List<object> results = new();
 static void Check(string id, bool acceptance, Func<bool> test) {
  try { results.Add(new { id, acceptance, passed=test(), error=(string?)null }); }
  catch(Exception e) { results.Add(new {id,acceptance,passed=false,error=e.GetType().Name}); }
 }
 public static string Run() { results.Clear();
'''
FOOTER='''return JsonSerializer.Serialize(new { build_passed=true, cases=results });
 }
}
'''
ORDER_HELPERS='''
public sealed class ShippingProbe : Ordering.IShipper {
 public string Name=>"probe"; public int Calls; public string LastService="";
 public string CreateLabel(string reference,string service) { Calls++; LastService=service; return "label:"+reference; }
}
'''
INVENTORY_HELPERS='''
public sealed class SupplierProbe : Inventory.ISupplier {
 public string Name=>"probe"; public bool Accept=true; public List<string> Calls=new();
 public bool PlaceOrder(string sku,int quantity) { Calls.Add(sku+":"+quantity); return Accept; }
}
'''


def spec():
    tasks=[]
    def add(id,target,family,requirement,edits,mutant,body,helpers=''):
        tasks.append(dict(task_id=id,target_id=target,family=family,requirement=requirement,
                          edits=edits,mutant_edits=mutant,tests=HEADER+body+FOOTER+helpers))
    dispatch_old='''        var service = SelectService(customer);'''
    dispatch_new='''        if (_blockedCountries.Contains(customer.Address.CountryCode))
            return "unserved";
        var service = SelectService(customer);'''
    add('GC01-dispatch-rejection','GC-01','stateful_validation',
        'Dispatch must reject destinations in the existing blocked-country set with "unserved", without invoking the shipper or recording a dispatch. Preserve existing duplicate-reference precedence, followed by blocked-customer precedence. A rejected reference may later be dispatched to a served destination. Preserve all other behaviour and public APIs; edit only OrderProcessor.cs.',
        [(dispatch_old,dispatch_new,1)],
        [('''        if (_blockedCountries.Contains(customer.Address.CountryCode))
            return "unserved";''','''        if (_blockedCountries.Contains(customer.Address.CountryCode)) { _dispatched.Add(order.Reference); return "unserved"; }''',1)],
        '''
 Check("rejection-has-no-side-effects-and-allows-retry",true,()=> {
  var s=new ShippingProbe(); var p=new Ordering.OrderProcessor(s); var o=new Ordering.Order{Reference="R"}; var c=new Ordering.Customer(); c.Address.CountryCode="kp";
  if(p.Dispatch(o,c)!="unserved" || s.Calls!=0 || p.DispatchedCount!=0) return false;
  c.Address.CountryCode="DE";
  return p.Dispatch(o,c)=="label:R" && s.Calls==1 && p.DispatchedCount==1;
 });
 Check("second-blocked-country",true,()=> {var s=new ShippingProbe();var p=new Ordering.OrderProcessor(s);var c=new Ordering.Customer();c.Address.CountryCode="SY";return p.Dispatch(new(){Reference="S"},c)=="unserved" && s.Calls==0;});
 Check("blocked-customer-priority",false,()=> {var s=new ShippingProbe();var p=new Ordering.OrderProcessor(s);var c=new Ordering.Customer{Tier=Ordering.CustomerTier.Blocked};c.Address.CountryCode="KP";return p.Dispatch(new(){Reference="B"},c)=="blocked"&&s.Calls==0;});
 Check("duplicate-priority",false,()=> {var s=new ShippingProbe();var p=new Ordering.OrderProcessor(s);var o=new Ordering.Order{Reference="A"};var c=new Ordering.Customer();p.Dispatch(o,c);c.Address.CountryCode="KP";return p.Dispatch(o,c)=="duplicate"&&s.Calls==1;});
 Check("wholesale-service",false,()=> {var s=new ShippingProbe();var p=new Ordering.OrderProcessor(s);p.Dispatch(new(){Reference="W"},new(){Tier=Ordering.CustomerTier.Wholesale});return s.LastService=="freight";});
''',ORDER_HELPERS)
    old='''    public bool CheckAddress(Address address)
    {''';new=old+'\n        var country = address.CountryCode?.Trim();'
    base=(EVIDENCE/'baseline/corpus/src/Ordering/OrderProcessor.cs').read_text()
    start=base.index(old);end=base.index('    // ---- tax ----',start)
    address_old=base[start:end];address_new=address_old.replace(old,new).replace('string.IsNullOrWhiteSpace(address.CountryCode)','string.IsNullOrWhiteSpace(country)').replace('_blockedCountries.Contains(address.CountryCode)','_blockedCountries.Contains(country!)').replace('address.CountryCode == "GB"','string.Equals(country, "GB", StringComparison.OrdinalIgnoreCase)')
    rateold='''    public decimal ResolveRate(string countryCode)
    {''';ratenew=rateold+'\n        countryCode = countryCode?.Trim()!;'
    add('GC01-country-policy','GC-01','cross_method_validation',
        'Treat leading/trailing whitespace and letter case consistently for country codes in ResolveRate and CheckAddress. Blank rate codes retain the fallback rate; blank address codes remain invalid. Apply the existing GB postcode-length rule case-insensitively after trimming, and reject the existing blocked countries after trimming. Tax and duty must inherit the normalized rate through their existing behaviour. Do not mutate caller-owned Address values or change other rules. Edit only OrderProcessor.cs.',
        [(address_old,address_new,1),(rateold,ratenew,1)],[(address_new,address_old,1)],
        '''
 Check("normalized-rate",true,()=>new Ordering.OrderProcessor(new ShippingProbe()).ResolveRate(" de ")==0.19m);
 Check("lowercase-gb-postcode-boundary",true,()=>!new Ordering.OrderProcessor(new ShippingProbe()).CheckAddress(new(){CountryCode=" gb ",City="London",PostalCode="1234"}));
 Check("trimmed-blocked-address",true,()=>!new Ordering.OrderProcessor(new ShippingProbe()).CheckAddress(new(){CountryCode=" kp ",City="City",PostalCode="12345"}));
 Check("tax-uses-normalized-rate",true,()=>{var p=new Ordering.OrderProcessor(new ShippingProbe());var c=new Ordering.Customer();c.Address.CountryCode=" de ";var o=new Ordering.Order();o.Lines.Add(new(){UnitPrice=100,Quantity=1});return p.ComputeTax(o,c)==19m;});
 Check("duty-uses-normalized-rate",true,()=>{var p=new Ordering.OrderProcessor(new ShippingProbe());var c=new Ordering.Customer();c.Address.CountryCode=" de ";var o=new Ordering.Order();o.Lines.Add(new(){UnitPrice=300,Quantity=1});return p.EstimateDuty(o,c)==28.50m;});
 Check("does-not-mutate-address",true,()=>{var a=new Ordering.Address{CountryCode=" de ",City="Berlin",PostalCode="12345"};var p=new Ordering.OrderProcessor(new ShippingProbe());return p.CheckAddress(a)&&a.CountryCode==" de ";});
 Check("fallback-retained",false,()=>new Ordering.OrderProcessor(new ShippingProbe()).ResolveRate("ZZ")==0.15m);
 Check("empty-address-invalid",false,()=>!new Ordering.OrderProcessor(new ShippingProbe()).CheckAddress(new(){CountryCode="",City="Paris",PostalCode="12345"}));
''',ORDER_HELPERS)
    add('GC06-delivery-cap','GC-06','stateful_validation',
        'ConfirmDelivery must never credit more stock than the pending quantity for that SKU. Credit min(delivered,pending); partial deliveries must retain the remaining pending amount, complete/oversized deliveries clear it. Nonpositive delivery or missing pending order remains false with no stock mutation. Supplier-rejected orders must not create pending quantities. Preserve public APIs and other behaviours; edit only StockController.cs.',
        [('item.OnHand += delivered;','item.OnHand += Math.Min(delivered, qty);',1)],
        [('if (delivered >= qty)','if (delivered > 0)',1)],
        '''
 Check("oversized-delivery-capped",true,()=>{var s=new SupplierProbe();var p=new Inventory.StockController(s);var i=new Inventory.StockItem{Sku="X",OnHand=10,ReorderPoint=20};return p.PlaceReorder(i)&&p.ConfirmDelivery(i,50)&&i.OnHand==40&&!p.ConfirmDelivery(i,1)&&i.OnHand==40;});
 Check("partial-then-oversized",true,()=>{var p=new Inventory.StockController(new SupplierProbe());var i=new Inventory.StockItem{Sku="X",OnHand=10,ReorderPoint=20};p.PlaceReorder(i);return p.ConfirmDelivery(i,5)&&i.OnHand==15&&p.ConfirmDelivery(i,50)&&i.OnHand==40&&!p.ConfirmDelivery(i,1);});
 Check("zero-does-not-clear-pending",false,()=>{var p=new Inventory.StockController(new SupplierProbe());var i=new Inventory.StockItem{Sku="X",OnHand=10,ReorderPoint=20};p.PlaceReorder(i);return !p.ConfirmDelivery(i,0)&&p.ConfirmDelivery(i,30)&&i.OnHand==40;});
 Check("rejected-order-has-no-pending",false,()=>{var p=new Inventory.StockController(new SupplierProbe{Accept=false});var i=new Inventory.StockItem{Sku="X",OnHand=10,ReorderPoint=20};return !p.PlaceReorder(i)&&!p.ConfirmDelivery(i,5)&&i.OnHand==10;});
 Check("missing-pending-no-mutation",false,()=>{var p=new Inventory.StockController(new SupplierProbe());var i=new Inventory.StockItem{Sku="X",OnHand=10};return !p.ConfirmDelivery(i,5)&&i.OnHand==10;});
''',INVENTORY_HELPERS)
    add('GC06-pack-size','GC-06','business_rule_change',
        'Positive ReorderQuantity results must be rounded UP to a multiple of five after applying existing eligibility/target/minimum rules. PlaceReorder must send that rounded amount and ConfirmDelivery must track that amount as pending. Existing zero/no-reorder outcomes remain unchanged. Supported quantities/stock values lie between 0 and 1000. Do not otherwise change delivery handling or other policies. Edit only StockController.cs.',
        [('        return qty;','        return ((qty + 4) / 5) * 5;',1)],
        [('return ((qty + 4) / 5) * 5;','return (qty / 5) * 5;',1)],
        '''
 Check("round-eleven-to-fifteen",true,()=>new Inventory.StockController(new SupplierProbe()).ReorderQuantity(new(){Sku="X",OnHand=9,ReorderPoint=10})==15);
 Check("fallback-rounding",true,()=>new Inventory.StockController(new SupplierProbe()).ReorderQuantity(new(){Sku="X",OnHand=18})==25);
 Check("supplier-and-pending-consistent",true,()=>{var s=new SupplierProbe();var p=new Inventory.StockController(s);var i=new Inventory.StockItem{Sku="X",OnHand=9,ReorderPoint=10};return p.PlaceReorder(i)&&s.Calls.SequenceEqual(new[]{"X:15"})&&p.ConfirmDelivery(i,11)&&p.ConfirmDelivery(i,4)&&!p.ConfirmDelivery(i,1)&&i.OnHand==24;});
 Check("exact-multiple",false,()=>new Inventory.StockController(new SupplierProbe()).ReorderQuantity(new(){Sku="X",OnHand=10,ReorderPoint=10})==10);
 Check("not-eligible-remains-zero",false,()=>new Inventory.StockController(new SupplierProbe()).ReorderQuantity(new(){Sku="X",OnHand=21,ReorderPoint=20})==0);
 Check("blank-sku-remains-zero",false,()=>new Inventory.StockController(new SupplierProbe()).ReorderQuantity(new(){Sku="",OnHand=0,ReorderPoint=20})==0);
''',INVENTORY_HELPERS)
    add('LM04-country-normalization','LM-04','input_validation',
        'VatResolver.Resolve must trim country codes and compare them case-insensitively. Preserve unknown/blank-country zero rates, nonpositive-net handling, government exemption, existing business discount threshold and high-value rate cap. Preserve exact decimal behaviour; do not add rounding or mutate Account. Edit only VatResolver.cs.',
        [('        switch (countryCode)','        switch (countryCode?.Trim().ToUpperInvariant())',1)],
        [('countryCode?.Trim().ToUpperInvariant()','countryCode?.Trim().ToLowerInvariant()',1)],
        '''
 Check("trim-and-case",true,()=>new Invoicing.VatResolver().Resolve(new(),100," de ")==19m);
 Check("business-policy-retained",true,()=>new Invoicing.VatResolver().Resolve(new(){Kind=Invoicing.AccountKind.Business},20000,"ie")==2300m);
 Check("cap-after-normalization",true,()=>new Invoicing.VatResolver().Resolve(new(),200000," fr ")==30000m);
 Check("government-exemption",false,()=>new Invoicing.VatResolver().Resolve(new(){Kind=Invoicing.AccountKind.Government},100,"DE")==0m);
 Check("unknown-country",false,()=>new Invoicing.VatResolver().Resolve(new(),100,"ZZ")==0m);
 Check("nonpositive-net",false,()=>new Invoicing.VatResolver().Resolve(new(),-10,"DE")==0m);
 Check("business-threshold-exclusive",false,()=>new Invoicing.VatResolver().Resolve(new(){Kind=Invoicing.AccountKind.Business},10000,"DE")==1900m);
''')
    add('LM04-new-jurisdiction','LM-04','feature_extension',
        'Add the exact country code NL with a base VAT rate of 21%. Existing government exemption, business-rate reduction and high-value rate cap must apply to NL in their current order. Preserve current case sensitivity and all other jurisdictions/unknown-country behaviour. This task is independent of country normalization. Edit only VatResolver.cs.',
        [('''            case "GB":''','''            case "NL":
                rate = 0.21m;
                break;
            case "GB":''',1)],
        [('rate = 0.21m;','rate = 0.20m;',1)],
        '''
 Check("new-base-rate",true,()=>new Invoicing.VatResolver().Resolve(new(),100,"NL")==21m);
 Check("new-business-rate",true,()=>new Invoicing.VatResolver().Resolve(new(){Kind=Invoicing.AccountKind.Business},20000,"NL")==2100m);
 Check("new-high-value-cap",true,()=>new Invoicing.VatResolver().Resolve(new(),200000,"NL")==30000m);
 Check("new-business-before-cap",true,()=>new Invoicing.VatResolver().Resolve(new(){Kind=Invoicing.AccountKind.Business},200000,"NL")==21000m);
 Check("existing-gb",false,()=>new Invoicing.VatResolver().Resolve(new(),100,"GB")==20m);
 Check("government-nl",false,()=>new Invoicing.VatResolver().Resolve(new(){Kind=Invoicing.AccountKind.Government},100,"NL")==0m);
 Check("unknown-stays-zero",false,()=>new Invoicing.VatResolver().Resolve(new(),100,"ZZ")==0m);
''')
    planner=(EVIDENCE/'baseline/corpus/src/Inventory/ReplenishmentPlanner.cs').read_text()
    add('LM05-sku-validation','LM-05','input_validation',
        'BuildPlan must ignore null/empty/whitespace-only SKUs. For otherwise eligible items, trim leading/trailing SKU whitespace in both supplier requests and returned plan entries, without mutating the StockItem. Preserve quantity calculations, season handling, item order, failure markers and the existing LARGE threshold. Edit only ReplenishmentPlanner.cs.',
        [('if (string.IsNullOrEmpty(item.Sku))','if (string.IsNullOrWhiteSpace(item.Sku))',1),
         ('            bool placed = supplier.PlaceOrder(item.Sku, orderQty);','            var sku = item.Sku.Trim();\n            bool placed = supplier.PlaceOrder(sku, orderQty);',1),
         ('$"{item.Sku}:','$"{sku}:',3)],
        [('var sku = item.Sku.Trim();','var sku = item.Sku;',1)],
        '''
 Check("trim-request-and-output",true,()=>{var s=new SupplierProbe();var i=new Inventory.StockItem{Sku=" X ",OnHand=0,ReorderPoint=5};var plan=new Inventory.ReplenishmentPlanner().BuildPlan(new[]{i},s,2);return plan.SequenceEqual(new[]{"X:10"})&&s.Calls.SequenceEqual(new[]{"X:10"})&&i.Sku==" X ";});
 Check("ignore-whitespace",true,()=>{var s=new SupplierProbe();return new Inventory.ReplenishmentPlanner().BuildPlan(new[]{new Inventory.StockItem{Sku="  ",OnHand=0,ReorderPoint=5}},s,2).Count==0&&s.Calls.Count==0;});
 Check("trim-failed-label",true,()=>{var s=new SupplierProbe{Accept=false};return new Inventory.ReplenishmentPlanner().BuildPlan(new[]{new Inventory.StockItem{Sku=" X ",OnHand=0,ReorderPoint=5}},s,2).SequenceEqual(new[]{"X:FAILED"});});
 Check("season-four-retained",false,()=>new Inventory.ReplenishmentPlanner().BuildPlan(new[]{new Inventory.StockItem{Sku="X",OnHand=0,ReorderPoint=5}},new SupplierProbe(),4).SequenceEqual(new[]{"X:15"}));
 Check("negative-onhand-skipped",false,()=>new Inventory.ReplenishmentPlanner().BuildPlan(new[]{new Inventory.StockItem{Sku="X",OnHand=-1,ReorderPoint=5}},new SupplierProbe(),2).Count==0);
 Check("large-threshold-retained",false,()=>new Inventory.ReplenishmentPlanner().BuildPlan(new[]{new Inventory.StockItem{Sku="X",OnHand=0,ReorderPoint=200}},new SupplierProbe(),2).SequenceEqual(new[]{"X:LARGE:250"}));
''',INVENTORY_HELPERS)
    aggregate='''namespace Inventory;
public sealed class ReplenishmentPlanner {
 public IReadOnlyList<string> BuildPlan(IEnumerable<StockItem> items, ISupplier supplier, int season) {
  var totals=new Dictionary<string,int>(StringComparer.Ordinal); var order=new List<string>();
  foreach(var item in items) {
   if(item.OnHand<0) continue;
   int available=item.OnHand-item.Reserved;
   if(available>item.ReorderPoint) continue;
   int deficit=item.ReorderPoint-available;
   int qty=deficit<=0?0:deficit<10?10:deficit<100?deficit:deficit+50;
   if(season==4 && qty>0) qty=(int)(qty*1.5); else if(season==1) qty/=2;
   if(qty<=0 || string.IsNullOrEmpty(item.Sku)) continue;
   if(!totals.ContainsKey(item.Sku)) {totals[item.Sku]=0;order.Add(item.Sku);}
   totals[item.Sku] += qty;
  }
  var plan=new List<string>();
  foreach(var sku in order) {
   int qty=totals[sku];bool placed=supplier.PlaceOrder(sku,qty);
   plan.Add(!placed?$"{sku}:FAILED":qty>200?$"{sku}:LARGE:{qty}":$"{sku}:{qty}");
  }
  return plan;
 }
}
'''
    add('LM05-supplier-batching','LM-05','feature_extension',
        'BuildPlan must aggregate eligible per-item replenishment quantities by exact SKU (ordinal case-sensitive) and make one supplier call and one result entry per SKU. Calculate each item quantity and seasonal adjustment exactly as before, THEN sum. Preserve order of first eligible occurrence. Apply FAILED/LARGE labelling to the aggregated request, with LARGE strictly above 200. Preserve existing invalid-item handling and do not mutate inputs. Quantities are bounded to avoid integer overflow. This task is independent of SKU normalization. Edit only ReplenishmentPlanner.cs.',
        [(planner,aggregate,1)], [('totals[item.Sku] += qty;','totals[item.Sku] = Math.Max(totals[item.Sku], qty);',1)],
        '''
 Check("aggregate-one-call",true,()=>{var s=new SupplierProbe();var items=new[]{new Inventory.StockItem{Sku="X",ReorderPoint=5},new Inventory.StockItem{Sku="X",ReorderPoint=5}};var r=new Inventory.ReplenishmentPlanner().BuildPlan(items,s,2);return r.SequenceEqual(new[]{"X:20"})&&s.Calls.SequenceEqual(new[]{"X:20"});});
 Check("season-before-sum",true,()=>{var s=new SupplierProbe();var items=new[]{new Inventory.StockItem{Sku="X",ReorderPoint=11},new Inventory.StockItem{Sku="X",ReorderPoint=11}};return new Inventory.ReplenishmentPlanner().BuildPlan(items,s,1).SequenceEqual(new[]{"X:10"})&&s.Calls.Count==1;});
 Check("aggregate-large-classification",true,()=>{var s=new SupplierProbe();var items=new[]{new Inventory.StockItem{Sku="X",ReorderPoint=100},new Inventory.StockItem{Sku="X",ReorderPoint=60}};return new Inventory.ReplenishmentPlanner().BuildPlan(items,s,2).SequenceEqual(new[]{"X:LARGE:210"});});
 Check("first-occurrence-and-case",true,()=>{var s=new SupplierProbe();var items=new[]{new Inventory.StockItem{Sku="B",ReorderPoint=5},new Inventory.StockItem{Sku="A",ReorderPoint=5},new Inventory.StockItem{Sku="B",ReorderPoint=5},new Inventory.StockItem{Sku="b",ReorderPoint=5}};return new Inventory.ReplenishmentPlanner().BuildPlan(items,s,2).SequenceEqual(new[]{"B:20","A:10","b:10"})&&s.Calls.SequenceEqual(new[]{"B:20","A:10","b:10"});});
 Check("one-failure-per-sku",true,()=>{var s=new SupplierProbe{Accept=false};var items=new[]{new Inventory.StockItem{Sku="X",ReorderPoint=5},new Inventory.StockItem{Sku="X",ReorderPoint=5}};return new Inventory.ReplenishmentPlanner().BuildPlan(items,s,2).SequenceEqual(new[]{"X:FAILED"})&&s.Calls.Count==1;});
 Check("unique-item-regression",false,()=>new Inventory.ReplenishmentPlanner().BuildPlan(new[]{new Inventory.StockItem{Sku="X",ReorderPoint=5}},new SupplierProbe(),4).SequenceEqual(new[]{"X:15"}));
 Check("invalid-item-regression",false,()=>new Inventory.ReplenishmentPlanner().BuildPlan(new[]{new Inventory.StockItem{Sku="X",OnHand=-1,ReorderPoint=5}},new SupplierProbe(),2).Count==0);
''',INVENTORY_HELPERS)
    return tasks


def main():
    pairs={p['target_id']:p for p in json.loads(PAIR_MANIFEST.read_text())['pairs']}
    generated=ROOT.parent/'generated/expanded-spec-v1';generated.mkdir(exist_ok=True)
    evidence=json.loads((EVIDENCE/'manifest.json').read_text())
    catalog=[]
    for task in spec():
        pair=pairs[task['target_id']];source_path=(ROOT.parent/pair['baseline_path']).resolve();source=source_path.read_text(encoding='utf-8-sig')
        if hashlib.sha256(source_path.read_bytes()).hexdigest()!=pair['baseline_sha256']:raise ValueError('Baseline changed')
        repair_path=(ROOT.parent/pair['repaired_path']).resolve()
        if hashlib.sha256(repair_path.read_bytes()).hexdigest()!=pair['repair_sha256']:raise ValueError('Repair changed')
        projectdir=generated/'sources'/source_path.parent.name;projectdir.mkdir(parents=True,exist_ok=True)
        for src in source_path.parent.rglob('*'):
            if src.is_file() and src.suffix in ['.cs','.csproj']:
                relative=str(src.relative_to(EVIDENCE/'baseline')).replace('\\','/')
                if hashlib.sha256(src.read_bytes()).hexdigest()!=evidence['baseline_files'][relative]:raise ValueError('Supporting source changed')
                destination=projectdir/src.relative_to(source_path.parent);destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,destination)
        repairs=generated/'sources/repairs';repairs.mkdir(exist_ok=True)
        shutil.copyfile(repair_path,repairs/(task['target_id']+'.cs'))
        reference=apply(source,task['edits']);mutant=apply(reference,task['mutant_edits'])
        taskdir=generated/task['task_id'];taskdir.mkdir(exist_ok=True)
        for name,text in [('reference.cs',reference),('mutant.cs',mutant),('tests.cs',task['tests'])]:(taskdir/name).write_text(text,encoding='utf-8')
        catalog.append({k:v for k,v in task.items() if k not in ['tests','edits','mutant_edits']}|dict(pair=pair,
            files={name:hashlib.sha256((taskdir/name).read_bytes()).hexdigest() for name in ['reference.cs','mutant.cs','tests.cs']},
            test_cases=task['tests'].count('\n Check('),
            snapshot_original=str((projectdir/source_path.name).relative_to(generated)).replace('\\','/'),
            snapshot_repaired='sources/repairs/'+task['target_id']+'.cs',admission='pending'))
    output=dict(schema_version='expanded-maintenance-spec/0.1',status='development_only_not_frozen_for_model_execution',
        source_hashes={str(p.relative_to(generated)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((generated/'sources').rglob('*')) if p.is_file()},
        selection='Purposive instrument expansion: 2 God Class + 2 Long Method targets, 3 projects. No metric/outcome-based repair selection.',tasks=catalog)
    (generated/'catalog.json').write_text(json.dumps(output,indent=2)+'\n')
    print(f'Materialised {len(catalog)} task specifications; no model calls.')

if __name__=='__main__':main()
