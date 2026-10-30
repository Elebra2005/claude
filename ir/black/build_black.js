const fs=require('fs'),path=require('path');
const {Document,Packer,Paragraph,TextRun,Table,TableRow,TableCell,WidthType,ShadingType,AlignmentType,HeadingLevel,ImageRun,LevelFormat,BorderStyle,Footer,PageNumber,VerticalAlign}=require('docx');
const D=process.argv[2]; // ir/black dir
const peaks=JSON.parse(fs.readFileSync(path.join(D,'peaks_black.json')));
const F="Calibri";
function runs(t,o={}){return t.split(/(\*\*[^*]+\*\*)/).filter(s=>s).map(s=>s.startsWith('**')?new TextRun({text:s.slice(2,-2),bold:true,font:F,size:o.size||22}):new TextRun({text:s,font:F,size:o.size||22}));}
const P=t=>new Paragraph({spacing:{after:120,line:276},alignment:AlignmentType.JUSTIFIED,children:runs(t)});
const B=t=>new Paragraph({numbering:{reference:"bul",level:0},spacing:{after:60},children:runs(t)});
const N=(t,r="num")=>new Paragraph({numbering:{reference:r,level:0},spacing:{after:60},children:runs(t)});
const H1=(t,pb)=>new Paragraph({heading:HeadingLevel.HEADING_1,keepNext:true,pageBreakBefore:!!pb,children:[new TextRun({text:t})]});
const H2=t=>new Paragraph({heading:HeadingLevel.HEADING_2,keepNext:true,children:[new TextRun({text:t})]});
const bd={style:BorderStyle.SINGLE,size:4,color:"A0A0A0"};const borders={top:bd,bottom:bd,left:bd,right:bd};
function table(head,rows,widths,o={}){
 const mk=(txt,w,isH,fill)=>new TableCell({borders,width:{size:w,type:WidthType.DXA},verticalAlign:VerticalAlign.CENTER,
  shading:{fill:isH?"1F4E79":(fill||"FFFFFF"),type:ShadingType.CLEAR,color:"auto"},margins:{top:o.m??50,bottom:o.m??50,left:80,right:80},
  children:[new Paragraph({spacing:{after:0},alignment:isH?AlignmentType.CENTER:AlignmentType.LEFT,children:isH?[new TextRun({text:txt,bold:true,color:"FFFFFF",font:F,size:o.hs||18})]:runs(String(txt),{size:o.s||18})})]});
 return new Table({width:{size:widths.reduce((a,b)=>a+b,0),type:WidthType.DXA},columnWidths:widths,
  rows:[new TableRow({tableHeader:true,children:head.map((h,i)=>mk(h,widths[i],true))}),...rows.map((r,ri)=>new TableRow({cantSplit:true,children:r.map((c,i)=>mk(c,widths[i],false,i===0&&o.first?"EAF1F8":(ri%2?"F7F7F7":"FFFFFF")))}))]});}
const cap=t=>new Paragraph({spacing:{before:60,after:200},children:[new TextRun({text:t,italics:true,font:F,size:19,color:"404040"})]});
const tcap=t=>new Paragraph({keepNext:true,spacing:{before:160,after:80},children:[new TextRun({text:t,bold:true,font:F,size:20})]});
const img=(f,wp,hp,w=620)=>new Paragraph({alignment:AlignmentType.CENTER,keepNext:true,spacing:{before:120,after:40},children:[new ImageRun({type:"png",data:fs.readFileSync(path.join(D,f)),transformation:{width:w,height:Math.round(w*hp/wp)},altText:{title:f,description:f,name:f}})]});
function assign(w){const r=[[3420,3460,"ν O–H (влага / гидратированный оксид)"],[2955,2965,"νₐₛ CH₃ (бутильная группа)"],[2930,2940,"νₐₛ CH₂"],[2870,2878,"νₛ CH₃"],[1718,1728,"ν C=O сложного эфира ароматической кислоты (фталат)"],[1597,1603,"ν C=C бензольного кольца (дублет фталата)"],[1577,1583,"ν C=C бензольного кольца (дублет фталата)"],[1485,1490,"колебание бензольного кольца"],[1460,1468,"δ CH₂ / δₐₛ CH₃"],[1380,1388,"δₛ CH₃"],[1352,1358,"ω CH₂"],[1270,1290,"νₐₛ C(=O)–O фталата — самая сильная полоса"],[1115,1122,"ν O–C–C сложного эфира"],[1068,1076,"ν O–C–C / колебание кольца фталата"],[1036,1042,"колебание кольца / C–O (н-бутил)"],[958,965,"колебание н-бутильной группы"],[937,945,"колебание н-бутильной группы"],[838,846,"колебание кольца фталата"],[735,745,"δ C–H 1,2-замещённого (орто) бензольного кольца — маркер фталатов"],[700,708,"деформационное колебание кольца фталата"],[645,655,"деформационное колебание кольца фталата"]];for(const[a,b,t]of r)if(w>=a&&w<=b)return t;return "—";}
const C=[];
C.push(new Paragraph({alignment:AlignmentType.CENTER,spacing:{before:1400,after:200},children:[new TextRun({text:"ОТЧЁТ",bold:true,size:44,font:F,color:"1F4E79"})]}));
C.push(new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:200},children:[new TextRun({text:"по результатам ИК-спектроскопического анализа",size:30,font:F})]}));
C.push(new Paragraph({alignment:AlignmentType.CENTER,spacing:{after:500},children:[new TextRun({text:"образца buryak_shmurdyak_black",size:30,font:F})]}));
C.push(table(["Параметр","Значение"],[["Объект","Образец buryak_shmurdyak_black (паста чёрного цвета)"],["Метод","ИК-Фурье спектроскопия, НПВО (алмазный кристалл)"],["Дата регистрации спектра","30.09.2026"],["Дата отчёта","30.10.2026"],["Задача","Определить органическую основу, добавки и неорганический компонент; сравнить с ранее исследованными тиоколами"],["ЯМР","Не проводился на момент отчёта; результаты будут добавлены отдельно"]],[3000,6638],{s:20,hs:20}));
C.push(H1("1. Краткие результаты",1));
C.push(P("Образец **не содержит тиокола**: в спектре нет ни формальных полос (1024, 949 см⁻¹), ни полос S–CH₂ (1410 см⁻¹), ни полосы концевых SH-групп (2560 см⁻¹). Органическая часть образца — **практически чистый дибутилфталат (ДБФ)**. Кроме него присутствует **чёрный неорганический компонент** с поглощением металл–кислород ниже 650 см⁻¹ — предположительно диоксид марганца MnO₂."));
C.push(P("По составу образец соответствует типичной **вулканизующей (отверждающей) пасте для тиоколовых герметиков** — суспензии диоксида марганца в дибутилфталате (тип пасты №9). Это второй компонент к тиоколовой основе, а не сама основа."));
C.push(table(["Компонент","Результат ИК","Комментарий"],[
 ["Дибутилфталат (ДБФ)","основной органический компонент, ≈95–100 % органической части","Полный набор полос фталата: 1723, 1600/1580, 1277, 1119, 1072, 742 см⁻¹; н-бутильные полосы 2960, 1384, 962/941 см⁻¹"],
 ["Неорганический компонент","присутствует, количество не определяется","Рост поглощения ниже 650 см⁻¹ (колебания M–O), чёрный цвет — предположительно MnO₂"],
 ["Тиокол","не обнаружен (< ≈5 %)","Нет полос 1024, 1410, 2560 см⁻¹"],
 ["Эпоксидная смола","не обнаружена","Нет полос 1510, 1244, 831 см⁻¹"],
 ["Хлорпарафин","не обнаружен","Нет отдельной полосы CHCl 1260–1270 см⁻¹ и прироста CH₂; окончательно — по ЯМР"],
 ["Полиуретан, лапрол","не обнаружены","Нет полос N–H и широкой полосы простого эфира"]],[2300,2700,4638],{first:true}));
C.push(H1("2. Методика"));
C.push(B("Спектр зарегистрирован методом НПВО (алмазный кристалл), 4000–550 см⁻¹, шаг 1 см⁻¹. Область ниже 560 см⁻¹ в анализе не использовалась (край пропускания)."));
C.push(B("Обработка та же, что и для образцов buryak_1t, 2t, 1p, 2x: перевод в оптическую плотность A = −lg(T/T₀) с T₀ в области 2000–2600 см⁻¹, поиск пиков после сглаживания Савицкого–Голея, вторая производная для разрешения перекрывающихся полос."));
C.push(B("Для проверки на тиокол спектр сопоставлен со спектром чистого тиокола buryak_1t из предыдущей серии."));
C.push(H1("3. ИК-спектр и его расшифровка"));
C.push(img("spectrum_black.png",2080,992));
C.push(cap("Рисунок 1. ИК-спектр (НПВО) образца buryak_shmurdyak_black с разметкой областей функциональных групп"));
C.push(P("**Расшифровка:**"));
C.push(B("**Сложный эфир ароматической кислоты.** Сильная полоса C=O при 1723 см⁻¹ вместе с полосами 1277 см⁻¹ (C(=O)–O) и 1119/1072 см⁻¹ (O–C–C) — классическая «тройка» полос эфиров фталевой кислоты."));
C.push(B("**Орто-замещённое бензольное кольцо.** Дублет 1600/1580 см⁻¹ равной интенсивности и сильная полоса 742 см⁻¹ — однозначные признаки фталата."));
C.push(B("**Бутильные группы.** Самая сильная полоса C–H при 2960 см⁻¹ (CH₃), полосы 2935/2874, 1384 см⁻¹ и пара 962/941 см⁻¹ указывают на н-бутильные радикалы. Признаков длинных алкильных цепей (как у диоктилфталата: сильная полоса 2858 см⁻¹) нет. Вывод — **дибутилфталат**."));
C.push(B("**Неорганический компонент.** Поглощение монотонно растёт ниже 650 см⁻¹ (колебания металл–кислород); вместе с чёрным цветом образца это указывает на оксид металла, предположительно MnO₂ — стандартный отвердитель тиоколов. Слабая широкая полоса около 3440 см⁻¹ — вода или гидроксильные группы на поверхности оксида."));
C.push(new Paragraph({keepNext:true,pageBreakBefore:true,spacing:{before:0,after:80},children:[new TextRun({text:"Таблица 1. Пики образца buryak_shmurdyak_black",bold:true,font:F,size:20})]}));
C.push(table(["ν, см⁻¹","A","Отнесение"],peaks.map(([w,a])=>[w,a.toFixed(3),assign(w)]),[1300,1300,7038],{s:16,hs:16,m:15}));
C.push(H1("4. Сравнение с тиоколом",1));
C.push(img("overlay_black_vs_1t.png",2080,992));
C.push(cap("Рисунок 2. Наложение спектров образца и чистого тиокола buryak_1t (оптическая плотность)"));
C.push(P("**Расшифровка.** Спектры принципиально различаются. Самая сильная полоса тиокола 1024 см⁻¹ в образце отсутствует; на её месте — слабый склон полос фталата. Совпадающих по форме и положению полос нет."));
C.push(img("zoom_black.png",2080,1280));
C.push(cap("Рисунок 3. Увеличенные диагностические области"));
C.push(P("**Расшифровка по панелям:**"));
C.push(B("**1800–1550 см⁻¹.** У образца — сильная C=O 1723 см⁻¹ и дублет 1600/1580 см⁻¹ (фталат); у тиокола в этой области полос нет."));
C.push(B("**1320–1000 см⁻¹.** Набор фталата (1277, 1119, 1072, 1039 см⁻¹) вместо набора формали тиокола (1110, 1069, 1024 см⁻¹). Полосы 1024 см⁻¹ нет — тиокола в образце менее ≈5 %."));
C.push(B("**1000–560 см⁻¹.** Полосы н-бутила 962/941 и орто-замещённого кольца 742 см⁻¹; ниже 650 см⁻¹ — рост поглощения неорганического компонента."));
C.push(B("**2640–2500 см⁻¹.** У тиокола видна полоса SH-групп около 2560 см⁻¹, у образца её нет."));
C.push(H1("5. Состав органической части",1));
C.push(P("Пересчёт на 100 % органической части. Неорганический компонент в расчёт не входит."));
C.push(table(["Компонент","ИК, %","ЯМР, %","Итог, %","Примечание"],[
 ["Дибутилфталат","≈95–100","ожидается","≈95–100","Единственный обнаруженный органический компонент"],
 ["Прочие органические добавки (стеариновая кислота и др.)","не обнаружены (< 2–3 %)","ожидается","< 3","В типовых пастах около 1 % стеариновой кислоты — ниже предела обнаружения ИК"],
 ["Тиокол","не обнаружен (< 5 %)","ожидается","< 5",""],
 ["Неорганический компонент (MnO₂?)","присутствует","—","вне 100 %","Количество — по зольности; природу металла — РФА"]],[2700,1700,1300,1300,2638],{first:true}));
C.push(H1("6. Выводы"));
C.push(N("Образец buryak_shmurdyak_black не является тиоколом: полос полисульфидного олигомера и SH-групп нет.","num2"));
C.push(N("Органическая часть — практически чистый дибутилфталат (≈95–100 %).","num2"));
C.push(N("Присутствует чёрный неорганический компонент — предположительно диоксид марганца.","num2"));
C.push(N("По составу образец соответствует вулканизующей пасте для тиоколовых герметиков (MnO₂ в ДБФ, тип пасты №9).","num2"));
C.push(N("Эпоксидная смола, хлорпарафины, полиуретаны и лапролы не обнаружены.","num2"));
C.push(H1("7. Рекомендации"));
C.push(table(["Задача","Метод"],[
 ["Подтвердить ДБФ, отличить от диизобутилфталата, проверить отсутствие хлорпарафина","ЯМР ¹H: ДБФ — 7,7/7,5 м.д. (аром.), 4,30 (т, OCH₂), 1,72, 1,45, 0,97 (т) м.д.; диизобутилфталат — 4,08 (д), 0,99 (д); хлорпарафин — широкие сигналы CHCl 3,8–4,5 м.д."],
 ["Определить металл неорганического компонента","РФА (ожидается Mn)"],
 ["Соотношение паста : ДБФ","Зольность (прокаливание): остаток ≈ доля неорганики"],
 ["Следы стеариновой кислоты и других добавок","ЯМР ¹H (сигналы 2,35 и 1,25 м.д.) или ГХ-МС экстракта"]],[3800,5838]));
const doc=new Document({styles:{default:{document:{run:{font:F,size:22}}},paragraphStyles:[
 {id:"Heading1",name:"Heading 1",basedOn:"Normal",next:"Normal",quickFormat:true,run:{size:30,bold:true,font:F,color:"1F4E79"},paragraph:{spacing:{before:280,after:140},outlineLevel:0}},
 {id:"Heading2",name:"Heading 2",basedOn:"Normal",next:"Normal",quickFormat:true,run:{size:25,bold:true,font:F,color:"2E75B6"},paragraph:{spacing:{before:200,after:100},outlineLevel:1}}]},
 numbering:{config:[{reference:"bul",levels:[{level:0,format:LevelFormat.BULLET,text:"•",alignment:AlignmentType.LEFT,style:{paragraph:{indent:{left:540,hanging:300}}}}]},
  {reference:"num",levels:[{level:0,format:LevelFormat.DECIMAL,text:"%1.",alignment:AlignmentType.LEFT,style:{paragraph:{indent:{left:540,hanging:360}}}}]},
  {reference:"num2",levels:[{level:0,format:LevelFormat.DECIMAL,text:"%1.",alignment:AlignmentType.LEFT,style:{paragraph:{indent:{left:540,hanging:360}}}}]}]},
 sections:[{properties:{page:{size:{width:11906,height:16838},margin:{top:1134,bottom:1134,left:1134,right:1134}}},
  footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({children:[PageNumber.CURRENT],font:F,size:18,color:"808080"})]})]})},children:C}]});
Packer.toBuffer(doc).then(b=>{fs.writeFileSync(path.join(D,'IR_report_black.docx'),b);console.log('ok')});
