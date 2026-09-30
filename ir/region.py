from load import *
import sys
lo,hi=int(sys.argv[1]),int(sys.argv[2]); step=int(sys.argv[3])
D={}
for k in NAMES:
    x,t=load(k); base=np.percentile(t[(x>2000)&(x<2600)],50)
    D[k]=(x,-np.log10(np.clip(t/base,1e-3,None)))
print("cm-1   "+"  ".join(f"{k:>6}" for k in NAMES))
for w in range(hi,lo-1,-step):
    print(f"{w:5d}  "+"  ".join(f"{np.interp(w,D[k][0][::-1],D[k][1][::-1]):6.3f}" for k in NAMES))
