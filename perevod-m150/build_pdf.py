# -*- coding: utf-8 -*-
"""Собирает PDF из M150_RU.md (кириллица + CJK-фолбэк)."""
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, PageBreak, KeepTogether, Image)

LIB = '/usr/share/fonts/truetype/liberation/'
pdfmetrics.registerFont(TTFont('Serif', LIB + 'LiberationSerif-Regular.ttf'))
pdfmetrics.registerFont(TTFont('Serif-Bold', LIB + 'LiberationSerif-Bold.ttf'))
pdfmetrics.registerFont(TTFont('Serif-It', LIB + 'LiberationSerif-Italic.ttf'))
pdfmetrics.registerFont(TTFont('Serif-BoldIt', LIB + 'LiberationSerif-BoldItalic.ttf'))
pdfmetrics.registerFontFamily('Serif', normal='Serif', bold='Serif-Bold',
                              italic='Serif-It', boldItalic='Serif-BoldIt')
pdfmetrics.registerFont(TTFont('Mono', LIB + 'LiberationMono-Regular.ttf'))
pdfmetrics.registerFont(TTFont('CJK', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'))

DARK, ACCENT, WARN = colors.HexColor('#1a1a1a'), colors.HexColor('#274b6d'), colors.HexColor('#8f1d1d')

def S(name, **kw):
    kw.setdefault('fontName', 'Serif'); kw.setdefault('textColor', DARK)
    return ParagraphStyle(name, **kw)

BODY   = S('body', fontSize=10, leading=14, alignment=TA_JUSTIFY, firstLineIndent=0.5*cm, spaceAfter=5)
PLAIN  = S('plain', fontSize=10, leading=14, spaceAfter=4)
H1     = S('h1', fontName='Serif-Bold', fontSize=17, leading=21, spaceBefore=6, spaceAfter=12, textColor=ACCENT)
H2     = S('h2', fontName='Serif-Bold', fontSize=13.5, leading=17, spaceBefore=13, spaceAfter=7, textColor=ACCENT)
H3     = S('h3', fontName='Serif-Bold', fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=5)
H4     = S('h4', fontName='Serif-Bold', fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=4)
QUOTE  = S('quote', fontSize=9.8, leading=13.5, textColor=WARN, leftIndent=0.35*cm,
           rightIndent=0.2*cm, spaceBefore=5, spaceAfter=7, alignment=TA_JUSTIFY)
LI     = S('li', fontSize=10, leading=13.5, spaceAfter=2.5, alignment=TA_JUSTIFY)
TH     = S('th', fontName='Serif-Bold', fontSize=8.6, leading=11)
TD     = S('td', fontSize=8.6, leading=11)
CAP    = S('cap', fontSize=8.8, leading=11.5, alignment=TA_CENTER,
           fontName='Serif-It', textColor=colors.HexColor('#444444'),
           spaceBefore=3, spaceAfter=10)
TITLE  = S('title', fontName='Serif-Bold', fontSize=22, leading=27, alignment=TA_CENTER,
           spaceAfter=10, textColor=ACCENT)
SUB    = S('sub', fontSize=13, leading=17, alignment=TA_CENTER, spaceAfter=6)

CJK = re.compile(r'([　-鿿＀-￯]+)')
INL = re.compile(r'(\*\*.+?\*\*|\*[^*\s][^*]*?\*|`[^`]+?`|\[[^\]]+?\]\([^)]*?\))')

def fmt(text):
    """markdown-инлайн → разметка reportlab, с подстановкой CJK-шрифта."""
    out = []
    for part in INL.split(text.replace('<br>', '\n')):
        if not part:
            continue
        esc = lambda s: s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        if part.startswith('**') and part.endswith('**'):
            out.append('<b>%s</b>' % esc(part[2:-2]))
        elif part.startswith('*') and part.endswith('*') and len(part) > 2:
            out.append('<i>%s</i>' % esc(part[1:-1]))
        elif part.startswith('`') and part.endswith('`'):
            out.append('<font name="Mono" size="9">%s</font>' % esc(part[1:-1]))
        elif part.startswith('['):
            m = re.match(r'\[([^\]]+)\]\([^)]*\)', part)
            out.append(esc(m.group(1) if m else part))
        else:
            out.append(esc(part))
    s = ''.join(out).replace('\n', '<br/>')
    return CJK.sub(r'<font name="CJK">\1</font>', s)

lines = open('M150_RU.md', encoding='utf-8').read().split('\n')
story, i, n, first_h1, cover = [], 0, len(lines), True, False
AVAIL = A4[0] - 4 * cm

while i < n:
    line = lines[i].rstrip()

    # --- рисунок ---
    mimg = re.match(r'^!\[(.*?)\]\((fig/[^)]+)\)\s*$', line)
    if mimg:
        cap, path = mimg.group(1), mimg.group(2)
        from PIL import Image as PILImage
        px_w, px_h = PILImage.open(path).size
        dpi = 200
        w = px_w / dpi * 72.0
        h = px_h / dpi * 72.0
        maxw, maxh = AVAIL, 20.5 * cm
        k = min(maxw / w, maxh / h, 1.0)
        w, h = w * k, h * k
        blk = [Image(path, width=w, height=h, hAlign='CENTER')]
        if cap:
            blk.append(Paragraph(fmt(cap), CAP))
        story += [Spacer(1, 5), KeepTogether(blk), Spacer(1, 3)]
        i += 1
        continue

    # --- таблица ---
    if line.startswith('|') and i + 1 < n and re.match(r'^\|[\s:|-]+\|$', lines[i + 1].strip()):
        rows = []
        while i < n and lines[i].strip().startswith('|'):
            raw = lines[i].strip().strip('|')
            if not re.match(r'^[\s:|-]+$', raw):
                rows.append([c.strip() for c in raw.split('|')])
            i += 1
        cols = max(len(r) for r in rows)
        rows = [r + [''] * (cols - len(r)) for r in rows]
        weights = [max(8, max(len(r[c]) for r in rows) ** 0.62) for c in range(cols)]
        total = sum(weights)
        widths = [AVAIL * w / total for w in weights]
        data = [[Paragraph(fmt(c), TH if ri == 0 else TD) for c in row]
                for ri, row in enumerate(rows)]
        t = Table(data, colWidths=widths, repeatRows=1, hAlign='CENTER')
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#8a8a8a')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e4e9ee')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f6f7f9')]),
        ]))
        story += [Spacer(1, 4), t, Spacer(1, 9)]
        continue

    if set(line.strip()) == {'-'} and len(line.strip()) >= 3:
        i += 1; continue

    # --- заголовки ---
    if line.startswith('#'):
        lvl = len(line) - len(line.lstrip('#'))
        txt = line.lstrip('#').strip()
        if lvl == 1:
            if first_h1:
                first_h1 = False
                story += [Spacer(1, 3.2 * cm), Paragraph(fmt(txt), TITLE)]
                cover = True
                i += 1
                continue
            story.append(PageBreak())
        if txt == 'Содержание':
            cover = False
            story.append(PageBreak())
        elif lvl == 2 and cover:
            story.append(Paragraph(fmt(txt), SUB))
            i += 1
            continue
        story.append(Paragraph(fmt(txt), {1: H1, 2: H2, 3: H3}.get(lvl, H4)))
        i += 1; continue

    # --- врезка/предупреждение ---
    if line.startswith('>'):
        buf = []
        while i < n and lines[i].startswith('>'):
            buf.append(re.sub(r'^#+\s*', '', lines[i].lstrip('>').strip()))
            buf = buf
            i += 1
        text = ' '.join(x for x in buf if x)
        if not text:
            continue
        cell = Paragraph(fmt(text), QUOTE)
        box = Table([[cell]], colWidths=[AVAIL], hAlign='CENTER')
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fbf4f4')),
            ('LINEBEFORE', (0, 0), (0, -1), 2.2, WARN),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story += [Spacer(1, 3), box, Spacer(1, 7)]
        continue

    # --- списки ---
    m = re.match(r'^(\s*)([-*]|\d+[.)])\s+(.*)$', line)
    if m:
        depth = len(m.group(1)) // 3
        marker = '•' if m.group(2)[0] in '-*' else m.group(2)
        st = ParagraphStyle('li%d' % depth, parent=LI,
                            leftIndent=(0.55 + 0.55 * depth) * cm,
                            bulletIndent=(0.15 + 0.55 * depth) * cm)
        story.append(Paragraph(fmt(m.group(3)), st, bulletText=marker))
        i += 1; continue

    if not line.strip():
        i += 1; continue

    # --- обычный абзац ---
    txt = line.strip()
    st = BODY if len(txt) > 90 else PLAIN
    story.append(Paragraph(fmt(txt), st))
    i += 1

# --- титульный блок и колонтитулы ---

def decorate(canv, doc):
    canv.saveState()
    if doc.page > 1:
        canv.setFont('Serif', 8)
        canv.setFillColor(colors.HexColor('#666666'))
        canv.drawCentredString(A4[0] / 2, 1.1 * cm, str(doc.page))
        canv.drawString(2 * cm, A4[1] - 1.25 * cm, 'M-150 — Руководство пользователя')
        canv.setStrokeColor(colors.HexColor('#c8c8c8'))
        canv.setLineWidth(0.4)
        canv.line(2 * cm, A4[1] - 1.45 * cm, A4[0] - 2 * cm, A4[1] - 1.45 * cm)
    canv.restoreState()

story.insert(3, Paragraph('Перевод с английского языка', SUB))

doc = BaseDocTemplate('M-150_Руководство_RU.pdf', pagesize=A4,
                      leftMargin=2 * cm, rightMargin=2 * cm,
                      topMargin=2 * cm, bottomMargin=1.8 * cm,
                      title='M-150 — Руководство пользователя (перевод с английского)',
                      author='RITON Additive Technology Co., Ltd.',
                      subject='Установка 3D-печати по металлу M-150')
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='main')
doc.addPageTemplates([PageTemplate(id='std', frames=[frame], onPage=decorate)])
doc.build(story)
print('готово')
