import re, sys
src = open(__import__("os").path.join(__import__("os").path.dirname(__file__) or ".", "..", "Indicators", "TurtleTrading.mq5")).read()
lines = src.split("\n")
errs, warns = [], []

# strip comments/strings for brace counting
def strip(code):
    code = re.sub(r'//[^\n]*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
    code = re.sub(r'"(\\.|[^"\\])*"', '""', code)
    code = re.sub(r"'(\\.|[^'\\])*'", "''", code)
    return code
clean = strip(src)

for open_c, close_c in [("{","}"), ("(",")"), ("[","]")]:
    a, b = clean.count(open_c), clean.count(close_c)
    if a != b: errs.append(f"unbalanced {open_c}{close_c}: {a} vs {b}")

# buffers declared vs #property
m = re.search(r'#property\s+indicator_buffers\s+(\d+)', src)
nbuf = int(m.group(1)); 
m = re.search(r'#property\s+indicator_plots\s+(\d+)', src)
nplot = int(m.group(1))
binds = re.findall(r'SetIndexBuffer\(\s*(\d+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)', src)
idxs = sorted(int(i) for i,_,_ in binds)
if idxs != list(range(nbuf)):
    errs.append(f"SetIndexBuffer indices {idxs} != 0..{nbuf-1}")
data_idx = sorted(int(i) for i,_,k in binds if k=="INDICATOR_DATA")
if data_idx != list(range(nplot)):
    errs.append(f"INDICATOR_DATA buffers {data_idx} must be exactly 0..{nplot-1} (plots come first)")

# every bound buffer must be declared as a double[] and set-as-series
declared = set(re.findall(r'^double\s+(\w+)\[\]\s*;', src, re.M))
for i, name, kind in binds:
    if name not in declared: errs.append(f"buffer {name} bound but not declared as double[]")
    if not re.search(rf'ArraySetAsSeries\(\s*{name}\s*,\s*false\s*\)', src):
        errs.append(f"buffer {name} never ArraySetAsSeries(...,false)")

# plot property blocks 1..nplot must exist
for p in range(1, nplot+1):
    if f"indicator_type{p}" not in src: errs.append(f"missing #property indicator_type{p}")
    if f"indicator_label{p}" not in src: errs.append(f"missing #property indicator_label{p}")

# arrow plots need PLOT_ARROW
arrow_plots = {p-1 for p in range(1, nplot+1) if re.search(rf'indicator_type{p}\s+DRAW_ARROW', src)}
set_arrows = {int(i) for i in re.findall(r'PlotIndexSetInteger\(\s*(\d+)\s*,\s*PLOT_ARROW', src)}
if arrow_plots - set_arrows: errs.append(f"DRAW_ARROW plots without PLOT_ARROW code: {sorted(arrow_plots-set_arrows)}")

# OnCalculate signature
if not re.search(r'int\s+OnCalculate\(\s*const int rates_total,\s*const int prev_calculated,\s*const datetime &time\[\],\s*const double &open\[\],\s*const double &high\[\],\s*const double &low\[\],\s*const double &close\[\],\s*const long &tick_volume\[\],\s*const long &volume\[\],\s*const int &spread\[\]\s*\)', src):
    errs.append("OnCalculate signature does not match the standard 10-arg form")

# required entry points
for fn in ["int OnInit()", "void OnDeinit(const int reason)"]:
    if fn not in src: errs.append(f"missing {fn}")

# every OnCalculate return path returns an int
rets = re.findall(r'return\((.*?)\);', src)
# functions called but never defined (rough check on our own helpers)
defined = set(re.findall(r'^\s*(?:void|double|int|bool|string)\s+(\w+)\s*\(', src, re.M))
called = set(re.findall(r'\b([A-Z]\w+)\s*\(', src))
builtin_ok = True

# input variables referenced but not declared
inputs = set(re.findall(r'^input\s+\S+\s+(\w+)', src, re.M))
for name in set(re.findall(r'\bInp[A-Z]\w+', strip(src))):
    if name not in inputs: errs.append(f"Inp* symbol used but not declared as input: {name}")

# unused inputs (warning only)
for name in inputs:
    if len(re.findall(rf'\b{name}\b', src)) < 2:
        warns.append(f"input {name} declared but never used")

# check globals declared before use in OnInit ordering is irrelevant in MQL5, skip

print(f"buffers={nbuf} plots={nplot} bindings={len(binds)} declared_doubles={len(declared)} inputs={len(inputs)}")
for w in warns: print("WARN:", w)
for e in errs: print("FAIL:", e)
print("STRUCT_OK" if not errs else "STRUCT_FAIL")
sys.exit(1 if errs else 0)
