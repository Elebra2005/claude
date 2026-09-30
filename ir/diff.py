from load import *
import sys
X=np.arange(560,4001)[::-1].astype(float)
def A(k):
    x,t=load(k); base=np.percentile(t[(x>2000)&(x<2600)],50)
    a=-np.log10(np.clip(t/base,1e-3,None)); return np.interp(X,x[::-1],a[::-1])
ref=A("1t")
# scale by 2860-2880 + 1400-1420 + 940-960 thiokol-specific bands
def scale(a):
    m=((X>1400)&(X<1420))|((X>940)&(X<960))
    return np.dot(a[m],ref[m])/np.dot(ref[m],ref[m])
R={}
for k in ["1p","2t","2x"]:
    a=A(k); s=scale(a); R[k]=a-s*ref; print(k,"scale",round(s,3))
lo,hi,st=map(int,sys.argv[1:4])
print("cm-1   "+"  ".join(f"{k:>7}" for k in R))
for w in range(hi,lo-1,-st):
    i=np.argmin(abs(X-w)); print(f"{w:5d}  "+"  ".join(f"{R[k][i]:7.3f}" for k in R))
