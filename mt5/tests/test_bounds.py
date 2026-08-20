import sys, random
sys.path.insert(0, __import__("os").path.dirname(__file__) or ".")
import turtle_ref
from turtle_ref import EMPTY

class StrictList(list):
    """Mimics an MQL5 array: negative or out-of-range index is a hard error."""
    def __getitem__(self, k):
        if isinstance(k, slice):
            if (k.start is not None and k.start < 0) or (k.stop is not None and k.stop < 0):
                raise IndexError(f"MQL5 out-of-range slice {k}")
            return list.__getitem__(self, k)
        if k < 0 or k >= len(self):
            raise IndexError(f"MQL5 array out of range: index {k}, size {len(self)}")
        return list.__getitem__(self, k)
    def __setitem__(self, k, v):
        if not isinstance(k, slice) and (k < 0 or k >= len(self)):
            raise IndexError(f"MQL5 array out of range: index {k}, size {len(self)}")
        return list.__setitem__(self, k, v)

# make every buffer the reset() creates a StrictList
_orig_reset = turtle_ref.Turtle.reset
def strict_reset(self, n):
    _orig_reset(self, n)
    for name in ("EU","ED","XU","XD","LE","SE","LX","SX","N","TRS","ST","EP","SP","LS"):
        setattr(self, name, StrictList(getattr(self, name)))
turtle_ref.Turtle.reset = strict_reset

def make_series(n, seed=1, drift=0.0, vol=1.0):
    random.seed(seed); px=100.0; O=[];H=[];L=[];C=[]
    for _ in range(n):
        op=px; cl=op+drift+random.gauss(0,vol)
        hi=max(op,cl)+abs(random.gauss(0,vol*0.5)); lo=min(op,cl)-abs(random.gauss(0,vol*0.5))
        O.append(op);H.append(hi);L.append(lo);C.append(cl); px=cl
    return StrictList(O),StrictList(H),StrictList(L),StrictList(C)

fails=[]
# sweep parameter combinations, including the smallest legal ones where
# warm-up indices are most likely to underflow
combos=[]
for e in (2,3,20,55):
    for x in (2,3,10,20):
        for a in (2,3,20):
            for ib in (True,False):
                combos.append(dict(entry=e, exit=x, atr=a, intrabar=ib, use_filter=True))
for kw in combos:
    for seed in (1,2,3):
        O,H,L,C = make_series(180, seed=seed, drift=0.1)
        try:
            t = turtle_ref.Turtle(**kw)
            t.calc(O,H,L,C,0)
            # then an incremental pass over the same data
            t2 = turtle_ref.Turtle(**kw)
            pc = t2.calc(O,H,L,C,0)
            t2.calc(O,H,L,C,pc)
        except IndexError as ex:
            fails.append((kw, seed, str(ex)))

print(f"swept {len(combos)*3} parameter/data combinations under strict MQL5 bounds")
if fails:
    for f in fails[:5]: print("FAIL:", f)
    print(f"RESULT: {len(fails)} OUT-OF-RANGE FAILURES")
    sys.exit(1)
print("RESULT: no array-out-of-range under any tested parameter set")
