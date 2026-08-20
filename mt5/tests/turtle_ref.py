"""Faithful port of TurtleTrading.mq5 OnCalculate, used to exercise the logic."""
import math
EMPTY = float('inf')

class Turtle:
    def __init__(self, entry=20, exit=10, atr=20, stopN=2.0,
                 intrabar=True, use_filter=True, point=0.0001):
        self.eP, self.xP, self.aP = entry, exit, atr
        self.stopN, self.intrabar, self.filt, self.pt = stopN, intrabar, use_filter, point
        self.start = max(entry, exit, atr) + 1
        self.reset(0)

    def reset(self, n):
        z = lambda v: [v]*n
        self.EU, self.ED, self.XU, self.XD = z(EMPTY), z(EMPTY), z(EMPTY), z(EMPTY)
        self.LE, self.SE, self.LX, self.SX = z(EMPTY), z(EMPTY), z(EMPTY), z(EMPTY)
        self.N, self.TRS = z(0.0), z(0.0)
        self.ST, self.EP, self.SP, self.LS = z(0.0), z(0.0), z(0.0), z(1.0)

    def calc(self, o, h, l, c, prev_calculated):
        rt = len(c)
        if rt < self.start + 2: return 0
        if prev_calculated == 0:
            self.reset(rt); first = 0
        else:
            first = prev_calculated - 1
        eP, xP, aP, pt = self.eP, self.xP, self.aP, self.pt

        for i in range(first, rt):
            # true range
            tr = h[0]-l[0] if i == 0 else max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
            # N (Wilder)
            if i < aP-1:
                self.TRS[i] = tr if i == 0 else self.TRS[i-1] + tr
                self.N[i] = 0.0
            elif i == aP-1:
                self.TRS[i] = self.TRS[i-1] + tr
                self.N[i] = self.TRS[i]/aP
            else:
                self.TRS[i] = self.TRS[i-1]
                self.N[i] = (self.N[i-1]*(aP-1) + tr)/aP

            if i < self.start:
                for b in (self.EU,self.ED,self.XU,self.XD,self.LE,self.SE,self.LX,self.SX): b[i] = EMPTY
                self.ST[i]=0.0; self.EP[i]=0.0; self.SP[i]=0.0; self.LS[i]=1.0
                continue

            upE = max(h[i-eP:i]); dnE = min(l[i-eP:i])
            upX = max(h[i-xP:i]); dnX = min(l[i-xP:i])
            self.EU[i], self.ED[i], self.XU[i], self.XD[i] = upE, dnE, upX, dnX
            self.LE[i]=self.SE[i]=self.LX[i]=self.SX[i]=EMPTY

            st  = int(self.ST[i-1]); ent = self.EP[i-1]
            stp = self.SP[i-1];      lsr = self.LS[i-1]
            n = self.N[i-1] if self.N[i-1] > 0 else self.N[i]
            off = 0.4*n if n > 0 else 5*pt
            acted = False

            if st != 0:
                isLong = st > 0; phantom = abs(st) == 2
                doExit = False; xpx = 0.0
                if isLong:
                    hitStop = (l[i] <= stp) if self.intrabar else (c[i] <= stp)
                    hitChan = (l[i] <  dnX) if self.intrabar else (c[i] <  dnX)
                    if hitStop or hitChan:
                        doExit = True
                        if self.intrabar:
                            fill = dnX - pt
                            xpx = stp if hitStop else fill
                            if hitStop and hitChan: xpx = max(stp, fill)
                        else: xpx = c[i]
                else:
                    hitStop = (h[i] >= stp) if self.intrabar else (c[i] >= stp)
                    hitChan = (h[i] >  upX) if self.intrabar else (c[i] >  upX)
                    if hitStop or hitChan:
                        doExit = True
                        if self.intrabar:
                            fill = upX + pt
                            xpx = stp if hitStop else fill
                            if hitStop and hitChan: xpx = min(stp, fill)
                        else: xpx = c[i]
                if doExit:
                    won = (xpx > ent) if isLong else (xpx < ent)
                    lsr = 0.0 if won else 1.0
                    if not phantom:
                        if isLong: self.LX[i] = h[i] + off
                        else:      self.SX[i] = l[i] - off
                    st = 0; ent = 0.0; stp = 0.0; acted = True

            if st == 0 and not acted:
                brkUp = (h[i] > upE) if self.intrabar else (c[i] > upE)
                brkDn = (l[i] < dnE) if self.intrabar else (c[i] < dnE)
                if brkUp and brkDn:
                    if c[i] >= o[i]: brkDn = False
                    else:            brkUp = False
                if brkUp or brkDn:
                    take = (not self.filt) or (lsr > 0.5)
                    if brkUp:
                        ent = (upE + pt) if self.intrabar else c[i]
                        stp = ent - self.stopN*n
                        st = 1 if take else 2
                        if take: self.LE[i] = l[i] - off
                    else:
                        ent = (dnE - pt) if self.intrabar else c[i]
                        stp = ent + self.stopN*n
                        st = -1 if take else -2
                        if take: self.SE[i] = h[i] + off
            self.ST[i]=float(st); self.EP[i]=ent; self.SP[i]=stp; self.LS[i]=lsr
        return rt

    def snapshot(self):
        return [tuple(b) for b in (self.EU,self.ED,self.XU,self.XD,
                                   self.LE,self.SE,self.LX,self.SX,
                                   self.N,self.TRS,self.ST,self.EP,self.SP,self.LS)]
