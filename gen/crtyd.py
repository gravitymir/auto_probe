import pcbnew, sys, itertools
b=pcbnew.LoadBoard(sys.argv[1]); tm=pcbnew.ToMM
items=[]
for fp in b.GetFootprints():
    for lay in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        try: poly = fp.GetCourtyard(lay)
        except Exception: continue
        if poly.OutlineCount()==0: continue
        bb=poly.BBox()
        items.append((fp.GetReference(), lay, (tm(bb.GetLeft()),tm(bb.GetTop()),tm(bb.GetRight()),tm(bb.GetBottom()))))
bad=[]
for (a,la,A),(c,lc,C) in itertools.combinations(items,2):
    if a==c or la!=lc: continue
    if A[0]<C[2] and C[0]<A[2] and A[1]<C[3] and C[1]<A[3]:
        ov=(min(A[2],C[2])-max(A[0],C[0]), min(A[3],C[3])-max(A[1],C[1]))
        bad.append((a,c,round(ov[0],2),round(ov[1],2)))
print("пересечений courtyard (один слой):",len(bad))
for x in sorted(set(bad))[:12]: print("  ",x)
