import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
HERE=os.path.dirname(os.path.abspath(__file__)); F="Arial"
wb=Workbook(); ws=wb.active; ws.title="Состав"
thin=Side(style="thin",color="A6A6A6"); B=Border(top=thin,bottom=thin,left=thin,right=thin)
hdr=PatternFill("solid",fgColor="1F4E79"); sfill=PatternFill("solid",fgColor="DDEBF7")
ws["A1"]="Состав органической части образца buryak_shmurdyak_black (в пересчёте на 100 % органики), ИК + ЯМР"; ws["A1"].font=Font(name=F,bold=True,size=13)
ws["A2"]="ИК (НПВО) и ЯМР ¹H/¹³C (CDCl₃; в архиве ЯМР образец NVM-tk-BD). Неорганический компонент в 100 % не входит. Строки «в т.ч.» — расшифровка по ЯМР, в сумму не входят."; ws["A2"].font=Font(name=F,italic=True,size=9,color="404040")
H=["Образец","Компонент","ИК, %","ЯМР, %","Среднее по ИК и ЯМР, %","Итог, % (сумма = 100)","Диапазон, %","Идентификация и комментарий","Неорганическая часть (не входит в 100 %)"]
r0=4
for j,h in enumerate(H,1):
    c=ws.cell(r0,j,h); c.font=Font(name=F,bold=True,color="FFFFFF",size=10); c.fill=hdr; c.border=B
    c.alignment=Alignment(wrap_text=True,vertical="center",horizontal="center")
rows=[("Фталатный пластификатор (технический ДБФ), сумма",97.5,97.2,"95–100","ИК: C=O 1723; 1600/1580; 1277, 1119, 1072; 742 см⁻¹; н-бутил 2960, 1384, 962/941 см⁻¹ (ИК-оценка 95–100 %, в расчёт взята середина). ЯМР ¹H: 7,71/7,52 (аром.), 4,30 (OCH₂), 1,72, 1,45, 0,96 м.д. — соотношение интегралов совпадает с ДБФ; ¹³C: 167,8; 132,4; 131,0; 128,9; 65,7; 30,7; 19,3; 13,8 м.д.","main"),
 ("   в т.ч. дибутилфталат","—",94.5,"","Основное вещество.","sub"),
 ("   в т.ч. метилбутилфталат (предположительно)","—",2.3,"","¹H: синглет O–CH₃ 3,92 м.д. Обычная технологическая примесь технического ДБФ.","sub"),
 ("   в т.ч. диизобутилфталат","—",0.5,"","¹H: O–CH₂ 4,08 м.д. (следы).","sub"),
 ("Полидиметилсилоксан (силикон)","признаки (плечо 1257–1260, полоса ≈800 см⁻¹)",2.2,"1,5–3","¹H: синглет Si–CH₃ 0,07 м.д.; ¹³C: 1,1 м.д. Силиконовая добавка (масло, антиадгезив, пеногаситель) либо загрязнение силиконовой смазкой при отборе пробы — проверить повторным отбором.","main"),
 ("Алифатические примеси","не видны",0.65,"< 1","¹H: слабые сигналы 0,8–1,35 м.д.; природа не установлена.","main"),
 ("Тиокол","не обнаружен (< 5 %)","не обнаружен (< 1 %)","—","ИК: нет 1024/949, 1410, 2560 см⁻¹. ЯМР: нет 4,70/3,72/2,89 м.д. и 95,5/66,2/38,9 м.д.","nd"),
 ("Хлорпарафин","не обнаружен","не обнаружен","—","ИК: нет CHCl 1260–1270 см⁻¹. ЯМР: нет CHCl 3,8–4,5 м.д. и 55–65 м.д.","nd"),
 ("Стеариновая кислота","ниже предела","не обнаружена","—","ЯМР: нет 2,35 м.д. и 180/34 м.д. Возможный стеарат марганца мог остаться в нерастворимом осадке.","nd"),
 ("Эпоксидная смола, полиуретан, лапрол","не обнаружены","не обнаружены","—","Нет характерных полос и сигналов.","nd")]
r=r0+1; start=r; main=[]
for comp,ir,nmr,rng,cmt,kind in rows:
    ws.cell(r,2,comp); ws.cell(r,3,ir); ws.cell(r,4,nmr); ws.cell(r,7,rng); ws.cell(r,8,cmt)
    if kind=="main":
        ws.cell(r,5,f'=IF(COUNT(C{r}:D{r})=0,"—",AVERAGE(C{r}:D{r}))'); main.append(r)
    elif kind=="sub":
        ws.cell(r,5,"—"); ws.cell(r,6,"—")
    else:
        ws.cell(r,5,"—"); ws.cell(r,6,"—")
    r+=1
end=r-1
S="SUM("+",".join(f"$E${m}" for m in main)+")"
for m in main: ws.cell(m,6,f"=E{m}/{S}")
ws.cell(start,1,"buryak_shmurdyak_black")
ws.cell(start,9,"Чёрный неорганический компонент: рост поглощения M–O ниже 650 см⁻¹ (ИК); в ЯМР не виден (нерастворим). Предположительно диоксид марганца MnO₂. Количество — по зольности, металл — РФА.")
ws.merge_cells(start_row=start,end_row=end,start_column=1,end_column=1); ws.merge_cells(start_row=start,end_row=end,start_column=9,end_column=9)
ws.cell(r,2,"Сумма органической части"); ws.cell(r,6,"=SUM("+",".join(f"F{m}" for m in main)+")")
for j in range(1,10):
    c=ws.cell(r,j); c.fill=sfill; c.font=Font(name=F,bold=True,size=9); c.border=B
ws.cell(r,6).number_format="0.0%"
for row in ws.iter_rows(min_row=start,max_row=end):
    for c in row:
        c.font=Font(name=F,size=9,bold=(c.column==1)); c.border=B
        c.alignment=Alignment(wrap_text=True,vertical="top",horizontal="center" if c.column in (3,4,5,6,7) else "left")
        if c.column in (3,4,5): c.number_format="0.0"
        if c.column==6: c.number_format="0.0%"; c.font=Font(name=F,size=10,bold=True)
for i,w in enumerate([14,30,12,11,12,12,10,70,26]): ws.column_dimensions[chr(65+i)].width=w
ws.row_dimensions[r0].height=42; ws.freeze_panes="C5"
n=r+2
ws.cell(n,1,"Вывод: образец — вулканизующая паста для тиоколовых герметиков (тип пасты №9: диоксид марганца в дибутилфталате), а не тиоколовая основа.").font=Font(name=F,bold=True,size=10)
ws.cell(n+1,1,"Итог = среднее по ИК и ЯМР, приведённое к сумме 100 %. Если компонент количественно определён одним методом, взято значение этого метода. Пределы обнаружения: ИК ≈2–5 %, ЯМР ¹H ≈0,5–1 %.").font=Font(name=F,italic=True,size=9)
ns=wb.create_sheet("Примечания")
notes=["Примечания к оценке состава",
"1. База пересчёта — 100 % органической части. Неорганический компонент исключён: в ЯМР он не виден, массовую долю даёт зольность, природу металла — РФА.",
"2. ИК: НПВО, алмазный кристалл, 4000–560 см⁻¹; сопоставление с чистым тиоколом buryak_1t.",
"3. ЯМР: Bruker 600 МГц, CDCl₃. ¹H — zg, 1 накопление (количественный режим); состав рассчитан по интегралам, на 1 молекулу ДБФ — 4 H сигнала O–CH₂ (4,30 м.д.). ¹³C — zgpg30, 1024 накопления (качественно). Калибровка: CHCl₃ 7,26 м.д., CDCl₃ 77,16 м.д.",
"4. ИК не различает ДБФ и его гомологи (метилбутил-, диизобутилфталат); их доли — только по ЯМР.",
"5. Силикон ≈2 %: требует проверки повторным отбором пробы без силиконовой смазки — возможна контаминация."]
for i,t in enumerate(notes,1):
    c=ns.cell(i,1,t); c.font=Font(name=F,bold=(i==1),size=12 if i==1 else 10); c.alignment=Alignment(wrap_text=True,vertical="top")
ns.column_dimensions["A"].width=120
for sh in (ws,ns):
    sh.page_setup.orientation="landscape"; sh.page_setup.paperSize=9; sh.page_setup.fitToWidth=1; sh.page_setup.fitToHeight=0; sh.sheet_properties.pageSetUpPr.fitToPage=True
wb.save(os.path.join(HERE,"Состав_buryak_shmurdyak_black_ИК_ЯМР.xlsx"))
