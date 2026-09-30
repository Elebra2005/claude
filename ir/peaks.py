from load import *
for k in NAMES:
    x,t=load(k)
    m=x>=560
    x,t=x[m],t[m]
    base=np.percentile(t[(x>2000)&(x<2600)],50)
    A=-np.log10(np.clip(t/base,1e-3,None))
    As=savgol_filter(A,9,2)
    p,_=find_peaks(As,prominence=0.004,distance=6)
    print(f"== {k}  baseline %T={base:.1f}  min %T={t.min():.1f} at {x[t.argmin()]:.0f}")
    print("  ".join(f"{x[i]:.0f}:{A[i]:.3f}" for i in p[::-1]))
