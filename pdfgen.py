"""Unicode report with language-aware labels and Arabic/Hebrew shaping."""
import os
from io import BytesIO
from fpdf import FPDF
import i18n


def _find_font():
    regular = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/arial.ttf']
    bold = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf']
    return next((p for p in regular if os.path.isfile(p)), None), next((p for p in bold if os.path.isfile(p)), None)


def build_report_pdf(user_name, bills, totals_by_cat):
    t = i18n.translate
    align = 'L' if i18n.language() == 'en' else 'R'
    pdf = FPDF()
    regular, bold = _find_font()
    if not regular:
        raise RuntimeError('A Unicode font is required for report export')
    pdf.add_font('Body', '', regular)
    pdf.add_font('Body', 'B', bold or regular)
    # HarfBuzz performs Arabic shaping and mixed-direction text layout.
    pdf.set_text_shaping(True)
    pdf.add_page()
    pdf.set_font('Body', 'B', 18)
    pdf.cell(0, 12, t('BillEase - דוח שנתי'), new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.set_font('Body', '', 11)
    pdf.cell(0, 8, t('שם המשתמש: {name}', name=user_name), new_x='LMARGIN', new_y='NEXT', align=align)
    pdf.ln(4)
    pdf.set_font('Body', 'B', 13)
    pdf.cell(0, 9, t('סיכום לפי קטגוריה'), new_x='LMARGIN', new_y='NEXT', align=align)
    pdf.set_font('Body', '', 11)
    currency = t('ש"ח')
    for category, total in totals_by_cat.items():
        pdf.cell(0, 7, f'{t(category)}: {total:.2f} {currency}',
                 new_x='LMARGIN', new_y='NEXT', align=align)
    pdf.ln(4)
    pdf.set_font('Body', 'B', 13)
    pdf.cell(0, 9, t('רשימת חשבונות'), new_x='LMARGIN', new_y='NEXT', align=align)
    columns = [('ספק', 55), ('סכום', 30), ('קטגוריה', 40), ('תאריך פירעון', 40), ('שולם', 25)]
    if i18n.language() != 'en':
        columns.reverse()
    pdf.set_font('Body', 'B', 9)
    for index, (label, width) in enumerate(columns):
        pdf.cell(width, 8, t(label), border=1, align='C',
                 new_x='LMARGIN' if index == 4 else 'RIGHT', new_y='NEXT' if index == 4 else 'TOP')
    pdf.set_font('Body', '', 9)
    for bill in bills:
        values = [str(bill.get('supplier', ''))[:26], f"{float(bill['amount']):.2f}",
                  t(bill.get('category') or ''), str(bill['due_date']), t('כן' if bill['is_paid'] else 'לא')]
        if i18n.language() != 'en':
            values.reverse()
        for index, ((label, width), value) in enumerate(zip(columns, values)):
            pdf.cell(width, 8, value, border=1, align='C',
                     new_x='LMARGIN' if index == 4 else 'RIGHT', new_y='NEXT' if index == 4 else 'TOP')
    result = BytesIO()
    pdf.output(result)
    result.seek(0)
    return result
