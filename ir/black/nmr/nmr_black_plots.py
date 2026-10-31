import os, json, sys
import numpy as np
from scipy.signal import find_peaks
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE=os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE,'proc_black_nmr.py')).read().split('if __name__')[0])
root=sys.argv[1]
plt.rcParams.update({"font.size":9,"axes.spines.top":False,"axes.spines.right":False,"axes.edgecolor":"#888"})
BL="#2a78d6"; LAB="#7a5a00"
# 1H
x,y=load(os.path.join(root,'NVM-tk-BD/1')); x=x+(7.26-calib(x,y,7.26,0.15))
def integ(a,b): m=(x>=a)&(x<=b); return float(np.trapezoid(y[m][::-1],x[m][::-1]))
ref=integ(4.20,4.42)/4
H=[("7,71","7.65,7.78","2","аром. CH (3,6) ДБФ"),("7,52","7.48,7.58","2","аром. CH (4,5) ДБФ"),("4,30","4.20,4.42","4","O–CH₂ ДБФ"),
   ("1,72","1.62,1.80","4","O–CH₂–CH₂ ДБФ"),("1,45","1.38,1.52","4","CH₂–CH₃ ДБФ"),("0,96","0.90,1.02","6","CH₃ ДБФ"),
   ("0,07","0.04,0.11","—","Si–CH₃ полидиметилсилоксана"),("4,08","4.05,4.11","—","O–CH₂ (диизобутилфталат?)"),("0,8–1,35*","0.80,0.89;1.15,1.36","—","алифатические примеси"),
   ("3,92","3.88,3.96","—","O–CH₃ (метилбутилфталат?)"),("5,32","5.30,5.34","—","CH₂Cl₂ (растворитель-примесь)")]
rows=[]
for d,rg,th,a in H:
    v=sum(integ(*map(float,s.split(','))) for s in rg.split(';'))/ref
    rows.append((d,round(v,3),th,a))
# mass estimate (per 1 molecule DBP = OCH2 4H)
pdms=[r for r in rows if r[0]=="0,07"][0][1]; dibp=[r for r in rows if r[0]=="4,08"][0][1]; ali=[r for r in rows if r[0].startswith("0,8")][0][1]
mbp=[r for r in rows if r[0]=="3,92"][0][1]/3
m_dbp=(4-2*mbp)/4*278.35; m_mbp=mbp*236.27; m_pdms=pdms/6*74.15; m_dibp=dibp/4*278.35; m_ali=ali/2*14.03
tot=m_dbp+m_mbp+m_pdms+m_dibp+m_ali
comp={"ДБФ":m_dbp/tot*100,"МБФ":m_mbp/tot*100,"ДИБФ":m_dibp/tot*100,"ПДМС":m_pdms/tot*100,"алиф. примеси":m_ali/tot*100}
print(rows); print({k:round(v,2) for k,v in comp.items()})
json.dump({"H1":rows,"comp":comp},open(os.path.join(HERE,'nmr_black_quant.json'),'w'),ensure_ascii=False,indent=1)
fig,ax=plt.subplots(figsize=(13,5.2)); m=(x>-0.3)&(x<8.3)
ax.plot(x[m],y[m]/y.max(),color=BL,lw=0.9)
for xp,lab in [(7.71,"аром. ДБФ"),(4.30,"O–CH₂"),(1.72,"CH₂"),(1.45,"CH₂"),(0.96,"CH₃"),(7.26,"CHCl₃"),(0.07,"Si–CH₃\n(ПДМС)")]:
    i=np.argmin(abs(x-xp)); ax.annotate(lab,(xp,y[i]/y.max()),xytext=(0,8),textcoords="offset points",ha="center",fontsize=8,color=LAB)
ax.set_xlim(8.3,-0.3); ax.set_ylim(-0.02,1.15); ax.set_xlabel("δ, м.д."); ax.set_ylabel("Интенсивность (норм.)")
ax.set_title("ЯМР ¹H (600 МГц, CDCl₃) — buryak_shmurdyak_black: дибутилфталат",loc="left",fontsize=11)
ins=ax.inset_axes([0.36,0.38,0.38,0.55]); mi=(x>-0.2)&(x<5.5)
ins.plot(x[mi],y[mi]/y.max()*100,color=BL,lw=0.7); ins.set_ylim(-0.2,4); ins.set_xlim(5.5,-0.2)
ins.set_title("×100: минорные сигналы",fontsize=7.5); ins.tick_params(labelsize=7)
for xp,lab,yy in [(5.32,"CH₂Cl₂",1.2),(4.08,"4,08",2.2),(3.92,"3,92 OCH₃",3.75),(1.25,"1,25",1.6),(0.85,"0,85",1.2),(0.07,"ПДМС",3.75)]:
    ins.annotate(lab,(xp,yy),ha="center",fontsize=6.5,color=LAB)
fig.tight_layout(); fig.savefig(os.path.join(HERE,"nmr_1H_black.png"),dpi=160); plt.close(fig)
# 13C
x,y=load(os.path.join(root,'NVM-tk-BD/2'))
mm=(x>74)&(x<80); p,_=find_peaks(y[mm],height=y[mm].max()*0.3,distance=20); x=x+(77.16-np.median(x[mm][p]))
noise=np.std(y[(x>185)&(x<220)])
fig,ax=plt.subplots(figsize=(13,4.8)); m=(x>-5)&(x<200)
ax.plot(x[m],y[m]/noise,color=BL,lw=0.8)
for xp,lab in [(167.82,"C=O"),(132.42,"C аром. четв."),(131.02,"CH аром."),(128.94,"CH аром."),(77.16,"CDCl₃"),(65.66,"O–CH₂"),(30.68,"CH₂"),(19.29,"CH₂"),(13.83,"CH₃"),(1.13,"Si–CH₃\n(ПДМС)")]:
    i=np.argmin(abs(x-xp)); ax.annotate(lab,(xp,y[i]/noise),xytext=(0,6),textcoords="offset points",ha="center",fontsize=8,color=LAB)
for xp,lab in [(95.5,"95,5 тиокол — нет"),(38.9,"38,9 тиокол — нет"),(60,"55–65 CHCl ХП — нет")]:
    ax.annotate(lab,(xp,40),ha="center",fontsize=7,color="#999",rotation=90,va="bottom")
ax.set_xlim(200,-5); ax.set_ylim(-20,600); ax.set_xlabel("δ, м.д."); ax.set_ylabel("Сигнал / шум")
ax.set_title("ЯМР ¹³C (151 МГц, CDCl₃) — buryak_shmurdyak_black",loc="left",fontsize=11)
fig.tight_layout(); fig.savefig(os.path.join(HERE,"nmr_13C_black.png"),dpi=160); plt.close(fig)
