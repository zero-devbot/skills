import math, random, sys
sys.path.insert(0, __import__("os").path.dirname(__file__) or ".")
from turtle_ref import Turtle, EMPTY

fails = []
def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -> " + detail))
    if not cond: fails.append(name)

def make_series(n, seed=1, drift=0.0, vol=1.0, start=100.0):
    random.seed(seed)
    o=h=l=c=[]; O=[];H=[];L=[];C=[]
    px = start
    for i in range(n):
        op = px
        mv = drift + random.gauss(0, vol)
        cl = op + mv
        hi = max(op, cl) + abs(random.gauss(0, vol*0.5))
        lo = min(op, cl) - abs(random.gauss(0, vol*0.5))
        O.append(op);H.append(hi);L.append(lo);C.append(cl)
        px = cl
    return O,H,L,C

# ---------------------------------------------------------------- T1: ATR matches Wilder reference
def wilder_atr(h,l,c,p):
    trs=[h[0]-l[0]]+[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    out=[0.0]*len(c); out[p-1]=sum(trs[:p])/p
    for i in range(p,len(c)): out[i]=(out[i-1]*(p-1)+trs[i])/p
    return out
O,H,L,C = make_series(400, seed=7)
t = Turtle(); t.calc(O,H,L,C,0)
ref = wilder_atr(H,L,C,20)
maxdiff = max(abs(t.N[i]-ref[i]) for i in range(19,400))
check("T1 N equals Wilder ATR(20)", maxdiff < 1e-12, f"maxdiff={maxdiff}")

# ---------------------------------------------------------------- T2: channel excludes the current bar
bad=[]
for i in range(t.start, 400):
    if t.EU[i] != max(H[i-20:i]): bad.append(("EU",i))
    if t.ED[i] != min(L[i-20:i]): bad.append(("ED",i))
    if t.XU[i] != max(H[i-10:i]): bad.append(("XU",i))
    if t.XD[i] != min(L[i-10:i]): bad.append(("XD",i))
check("T2 Donchian channels exclude the signal bar", not bad, str(bad[:3]))
# and prove it is not the naive inclusive version
incl = [i for i in range(t.start,400) if t.EU[i] == max(H[i-19:i+1]) and max(H[i-19:i+1]) != max(H[i-20:i])]
check("T2b channel differs from inclusive variant somewhere", len(incl)==0)

# ---------------------------------------------------------------- T3: incremental == full recompute
def full(series, **kw):
    O,H,L,C = series; t=Turtle(**kw); t.calc(O,H,L,C,0); return t.snapshot()
def incremental(series, **kw):
    O,H,L,C = series; t=Turtle(**kw)
    n0 = t.start+5
    pc = t.calc(O[:n0],H[:n0],L[:n0],C[:n0],0)
    for k in range(n0, len(C)+1):
        # terminal calls with the growing history; prev_calculated = bars done last time
        pc = t.calc(O[:k],H[:k],L[:k],C[:k],pc)
        # extend the buffers the way the terminal grows them
        if k < len(C):
            for b in (t.EU,t.ED,t.XU,t.XD,t.LE,t.SE,t.LX,t.SX): b.append(EMPTY)
            for b in (t.N,t.TRS,t.ST,t.EP,t.SP): b.append(0.0)
            t.LS.append(1.0)
    return t.snapshot()
series = make_series(300, seed=11)
for label, kw in [("sys1", dict()), ("sys2", dict(entry=55,exit=20,use_filter=False)),
                  ("close", dict(intrabar=False))]:
    a, b = full(series, **kw), incremental(series, **kw)
    same = all(a[j][i]==b[j][i] for j in range(14) for i in range(len(a[0])))
    diff = "" if same else str([(j,i,a[j][i],b[j][i]) for j in range(14) for i in range(len(a[0])) if a[j][i]!=b[j][i]][:3])
    check(f"T3 incremental == full recompute ({label})", same, diff)

# ---------------------------------------------------------------- T4: state machine invariants
def invariants(t, n):
    errs=[]
    for i in range(t.start, n):
        st=int(t.ST[i])
        if st not in (0,1,-1,2,-2): errs.append(f"bar {i} bad state {st}")
        if st==0 and (t.EP[i]!=0.0 or t.SP[i]!=0.0): errs.append(f"bar {i} flat but entry/stop set")
        if st!=0 and t.EP[i]==0.0: errs.append(f"bar {i} in position with no entry price")
        if st>0 and t.SP[i]>=t.EP[i]: errs.append(f"bar {i} long stop above entry")
        if st<0 and t.SP[i]<=t.EP[i]: errs.append(f"bar {i} short stop below entry")
        # never an entry and an exit arrow on the same bar
        ent = (t.LE[i]!=EMPTY) or (t.SE[i]!=EMPTY)
        ext = (t.LX[i]!=EMPTY) or (t.SX[i]!=EMPTY)
        if ent and ext: errs.append(f"bar {i} entry and exit on the same bar")
        # arrows only when state actually changed
        if t.LE[i]!=EMPTY and int(t.ST[i])!=1: errs.append(f"bar {i} long arrow but state {t.ST[i]}")
        if t.SE[i]!=EMPTY and int(t.ST[i])!=-1: errs.append(f"bar {i} short arrow but state {t.ST[i]}")
        if t.LX[i]!=EMPTY and int(t.ST[i-1])!=1: errs.append(f"bar {i} long exit but prev state {t.ST[i-1]}")
        if t.SX[i]!=EMPTY and int(t.ST[i-1])!=-1: errs.append(f"bar {i} short exit but prev state {t.ST[i-1]}")
    return errs
allerr=[]
for seed in range(1, 26):
    for kw in [dict(), dict(entry=55,exit=20,use_filter=False), dict(intrabar=False),
               dict(entry=55,exit=20,use_filter=False,intrabar=False)]:
        O,H,L,C = make_series(500, seed=seed, drift=(seed%5-2)*0.05, vol=1.0)
        t=Turtle(**kw); t.calc(O,H,L,C,0); allerr += invariants(t,500)
check("T4 state-machine invariants over 100 random runs", not allerr, str(allerr[:4]))

# ---------------------------------------------------------------- T5: entries actually fire and pair with exits
O,H,L,C = make_series(600, seed=3, drift=0.15, vol=1.0)
t=Turtle(); t.calc(O,H,L,C,0)
nLE=sum(1 for v in t.LE if v!=EMPTY); nSE=sum(1 for v in t.SE if v!=EMPTY)
nLX=sum(1 for v in t.LX if v!=EMPTY); nSX=sum(1 for v in t.SX if v!=EMPTY)
check("T5 uptrend produces long entries", nLE>0, f"LE={nLE}")
check("T5b each closed real trade has one exit", abs((nLE+nSE)-(nLX+nSX))<=1,
      f"entries={nLE+nSE} exits={nLX+nSX}")

# ---------------------------------------------------------------- T6: System 1 filter skips after a winner
t1=Turtle(use_filter=True); t1.calc(O,H,L,C,0)
t2=Turtle(use_filter=False); t2.calc(O,H,L,C,0)
e1=sum(1 for v in t1.LE if v!=EMPTY)+sum(1 for v in t1.SE if v!=EMPTY)
e2=sum(1 for v in t2.LE if v!=EMPTY)+sum(1 for v in t2.SE if v!=EMPTY)
check("T6 winner-filter takes strictly fewer trades", e1 < e2, f"filtered={e1} unfiltered={e2}")
phantoms=sum(1 for v in t1.ST if abs(int(v))==2)
check("T6b phantom trades are tracked", phantoms>0, f"phantom bars={phantoms}")
# after a phantom/real winner the very next breakout must be skipped
viol=[]
for i in range(t1.start+1,600):
    if int(t1.ST[i-1])==0 and int(t1.ST[i]) in (1,-1) and t1.LS[i-1]<0.5:
        viol.append(i)
check("T6c no real entry taken while last trade was a winner", not viol, str(viol[:3]))

# ---------------------------------------------------------------- T7: degenerate inputs
flat=[100.0]*300
t=Turtle(); t.calc(flat,flat,flat,flat,0)
sig=sum(1 for v in t.LE+t.SE+t.LX+t.SX if v!=EMPTY)
check("T7 flat market emits no signals and no NaN", sig==0 and all(not math.isnan(v) for v in t.N), f"signals={sig}")
# single huge gap bar
O,H,L,C = make_series(300, seed=5)
H[200]+=500; C[200]+=500; O[200]+=500; L[200]+=400
t=Turtle(); rc=t.calc(O,H,L,C,0)
check("T7b outlier bar handled without crash", rc==300 and all(math.isfinite(v) for v in t.N))
# too-few bars
t=Turtle(); check("T7c short history returns 0", t.calc(O[:5],H[:5],L[:5],C[:5],0)==0)

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILING: {fails}")
sys.exit(1 if fails else 0)
