import sys, math, itertools, pcbnew
tomm=pcbnew.ToMM
def rect(cx,cy,w,h,ang):
    a=math.radians(-ang); ca,sa=math.cos(a),math.sin(a)
    return [(cx+dx*ca-dy*sa, cy+dx*sa+dy*ca) for dx,dy in
            ((-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2))]
def sat(A,B,gap=0.0):
    """Возвращает глубину проникновения (мм) или 0, если не пересекаются."""
    best=1e9
    for P,Q in ((A,B),(B,A)):
        for i in range(4):
            ex,ey=P[(i+1)%4][0]-P[i][0], P[(i+1)%4][1]-P[i][1]
            nx,ny=-ey,ex; L=math.hypot(nx,ny) or 1; nx,ny=nx/L,ny/L
            a=[p[0]*nx+p[1]*ny for p in P]; b=[p[0]*nx+p[1]*ny for p in Q]
            if min(a)-gap > max(b) or min(b)-gap > max(a): return 0.0
            best=min(best, min(max(a)-min(b), max(b)-min(a)))
    return best
b=pcbnew.LoadBoard(sys.argv[1])
LAY=(pcbnew.F_SilkS,pcbnew.B_SilkS)
texts={l:[] for l in LAY}; pads={l:[] for l in LAY}
def addtxt(t,name):
    if t.GetLayer() not in LAY or not t.IsVisible(): return
    bx=t.GetTextBox(); p=t.GetPosition()
    texts[t.GetLayer()].append((rect(tomm(p.x),tomm(p.y),tomm(bx.GetWidth()),tomm(bx.GetHeight()),
                                     t.GetTextAngleDegrees()), name))
for fp in b.GetFootprints():
    addtxt(fp.Reference(), fp.GetReference()+':ref')
    addtxt(fp.Value(), fp.GetReference()+':val')
    for p in fp.Pads():
        ls=set(p.GetLayerSet().Seq()); sz=p.GetSize()
        for cu,sk in ((pcbnew.F_Cu,pcbnew.F_SilkS),(pcbnew.B_Cu,pcbnew.B_SilkS)):
            if cu in ls:
                q=p.GetPosition()
                pads[sk].append((rect(tomm(q.x),tomm(q.y),tomm(sz.x),tomm(sz.y),p.GetOrientationDegrees()),
                                 fp.GetReference()+'.'+p.GetNumber()))
for d in b.GetDrawings():
    if d.GetClass()=='PCB_TEXT': addtxt(d, '"%s"'%d.GetText())
THR=float(sys.argv[2]) if len(sys.argv)>2 else 0.0
ov=[];op=[]
for l in LAY:
    for (A,na),(B,nb) in itertools.combinations(texts[l],2):
        d=sat(A,B)
        if d>THR: ov.append((round(d,2),na,nb))
    for (A,na) in texts[l]:
        for (B,nb) in pads[l]:
            d=sat(A,B)
            if d>THR: op.append((round(d,2),na,nb))
print('надписей: %d | наложений текст-текст: %d | текст поверх пада: %d'
      % (sum(len(texts[l]) for l in LAY), len(ov), len(op)))
ov.sort(reverse=True)
op.sort(reverse=True)
for x in ov: print('   TT %5.2f мм  %s <-> %s' % x)
for x in op: print('   TP %5.2f мм  %s <-> %s' % x)
