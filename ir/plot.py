from load import *
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.size":9,"axes.spines.top":False,"axes.spines.right":False,
    "axes.edgecolor":"#888","axes.labelcolor":"#333","xtick.color":"#555","ytick.color":"#555"})
COL={"1p":"#2a78d6","1t":"#eb6834","2t":"#1baf7a","2x":"#e87ba4"}
TITLE={"1p":"buryak_1p","1t":"buryak_1t","2t":"buryak_2t","2x":"buryak_2x"}
# (lo, hi, label, color)
ZONES=[(3200,3600,"ν O–H / N–H","#9ec5f4"),
 (2800,3000,"ν C–H (CH₂, CH₃)","#cfcfcf"),
 (2540,2600,"ν S–H (концевые SH)","#f6d36b"),
 (1700,1760,"ν C=O эфир/уретан/ДБФ","#f4a6a6"),
 (1590,1615,"аром. C=C 1608","#b9e4c9"),
 (1500,1520,"аром. 1510 (бисфенол А)","#b9e4c9"),
 (1400,1470,"δ CH₂ / S–CH₂ 1410","#d9d2f0"),
 (1270,1300,"ω S–CH₂ 1283","#fbd3b0"),
 (1230,1255,"Ar–O–C 1244 (эпоксид)","#b9e4c9"),
 (1000,1160,"ν C–O–C формаль 1024/1069/1110","#cde2fb"),
 (935,960,"формаль 949","#cde2fb"),
 (905,920,"эпоксицикл 915","#b9e4c9"),
 (820,840,"п-замещ. бензол 831","#b9e4c9"),
 (560,800,"C–Cl (ХП) / M–O наполнитель","#e5e5e5")]
def dat(k):
    x,t=load(k); m=x>=560; return x[m],t[m]
def shade(ax,labels=True,ytxt=None):
    tier=0
    for lo,hi,lab,c in ZONES:
        ax.axvspan(lo,hi,color=c,alpha=.45,lw=0,zorder=0)
        if labels:
            if hi>1800: y=ytxt
            else: y=ytxt+0.055*(tier%5); tier+=1
            xc=(lo+hi)/2
            if hi<=1800 and hi-lo<150:
                ax.plot([xc,xc],[1.0,y],color="#999",lw=.5,transform=ax.get_xaxis_transform(),clip_on=False)
            ax.text(xc,y,lab,ha="center",va="bottom",fontsize=6.8,color="#333",
                    bbox=dict(fc="white",ec="none",pad=0.5),transform=ax.get_xaxis_transform())
def pk(x,t):
    base=np.percentile(t[(x>2000)&(x<2600)],50); A=-np.log10(np.clip(t/base,1e-3,None))
    p,_=find_peaks(savgol_filter(A,9,2),prominence=.004,distance=6); return p
# 1) individual spectra
for k in NAMES:
    x,t=dat(k)
    fig,ax=plt.subplots(figsize=(13,6.2))
    shade(ax,ytxt=1.005)
    ax.plot(x,t,color=COL[k],lw=1.4,zorder=3)
    for i in pk(x,t):
        if x[i]>2000 and x[i]<2800: continue
        ax.annotate(f"{x[i]:.0f}",(x[i],t[i]),xytext=(0,-12),textcoords="offset points",ha="center",fontsize=7,color="#222",rotation=90,va="top")
    ax.set_xlim(4000,560); ax.set_ylim(min(t.min()-12,20),max(t.max()+2,106))
    ax.set_xlabel("Волновое число, см⁻¹"); ax.set_ylabel("Пропускание, %T")
    ax.set_title(f"ИК-спектр (НПВО) — {TITLE[k]}",loc="left",pad=120,fontsize=11,color="#111")
    ax.grid(axis="x",color="#eee",lw=.6)
    fig.tight_layout(); fig.savefig(f"spectrum_{k}.png",dpi=160); plt.close(fig)
# 2) overlay absorbance, normalised to thiokol formal band 949
fig,ax=plt.subplots(figsize=(13,6.2)); shade(ax,ytxt=1.005)
for k in NAMES:
    x,t=dat(k); base=np.percentile(t[(x>2000)&(x<2600)],50); A=-np.log10(np.clip(t/base,1e-3,None))
    n=A[(x>940)&(x<958)].max(); ax.plot(x,A/n,color=COL[k],lw=1.3,label=TITLE[k],zorder=3)
ax.set_xlim(4000,560); ax.set_xlabel("Волновое число, см⁻¹"); ax.set_ylabel("Оптическая плотность (норм. на полосу формали 949 см⁻¹)")
ax.set_title("Наложение всех образцов (абсорбция, нормировка на тиокол)",loc="left",pad=120,fontsize=11)
ax.legend(frameon=False,loc="upper left"); fig.tight_layout(); fig.savefig("overlay_all.png",dpi=160); plt.close(fig)
# 3) difference spectra vs 1t
X=np.arange(560,4001)[::-1].astype(float)
def Ai(k):
    x,t=load(k); base=np.percentile(t[(x>2000)&(x<2600)],50)
    a=-np.log10(np.clip(t/base,1e-3,None)); return np.interp(X,x[::-1],a[::-1])
ref=Ai("1t"); m=((X>1400)&(X<1420))|((X>940)&(X<960))
fig,axs=plt.subplots(3,1,figsize=(13,9),sharex=True)
for ax,k in zip(axs,["1p","2t","2x"]):
    a=Ai(k); s=np.dot(a[m],ref[m])/np.dot(ref[m],ref[m]); d=a-s*ref
    shade(ax,labels=(ax is axs[0]),ytxt=1.02)
    ax.axhline(0,color="#999",lw=.6); ax.plot(X,d,color=COL[k],lw=1.3,zorder=3)
    ax.set_ylim(-0.02,max(0.1,d[X>600].max()*1.1))
    ax.text(0.005,0.85,f"{TITLE[k]} − {s:.2f}×buryak_1t   (доля тиокольной основы ≈ {s*100:.0f}% от 1t)",transform=ax.transAxes,fontsize=9,color="#111")
    ax.set_ylabel("ΔA")
axs[0].set_title("Разностные спектры: образец минус чистый тиокол (1t) — показывают только добавки",loc="left",pad=120,fontsize=11)
axs[-1].set_xlim(4000,560); axs[-1].set_xlabel("Волновое число, см⁻¹")
fig.tight_layout(); fig.savefig("difference_vs_1t.png",dpi=160); plt.close(fig)
# 4) zooms
fig,axs=plt.subplots(2,2,figsize=(13,8))
for ax,(lo,hi,tt) in zip(axs.flat,[(1450,1800,"Карбонилы и ароматика (ДБФ 1720+1600/1580; ЭД 1608/1510; уретан 1700–1730/1530)"),
    (1150,1320,"S–CH₂ 1283, Ar–O–C 1244 (эпоксид), CHCl 1260–1270 (хлорпарафин)"),
    (560,960,"Формаль 949, эпоксицикл 915, п-бензол 831, ДБФ 743, C–Cl 600–800"),
    (2500,2640,"S–H 2560–2570 (концевые меркаптогруппы)")]):
    for k in NAMES:
        x,t=dat(k); base=np.percentile(t[(x>2000)&(x<2600)],50); A=-np.log10(np.clip(t/base,1e-3,None))
        n=A[(x>940)&(x<958)].max(); mm=(x>=lo)&(x<=hi); ax.plot(x[mm],A[mm]/n,color=COL[k],lw=1.4,label=TITLE[k])
    for zlo,zhi,lab,c in ZONES:
        if zhi>lo and zlo<hi: ax.axvspan(max(zlo,lo),min(zhi,hi),color=c,alpha=.45,lw=0,zorder=0)
    ax.set_xlim(hi,lo); ax.set_title(tt,fontsize=8.5,loc="left"); ax.set_xlabel("см⁻¹")
axs[0,0].legend(frameon=False,fontsize=8)
fig.suptitle("Увеличенные диагностические области (A, норм. на 949 см⁻¹)",x=0.01,ha="left",fontsize=11)
fig.tight_layout(); fig.savefig("zoom_regions.png",dpi=160); plt.close(fig)
