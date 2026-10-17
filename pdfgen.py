# builds a simple PDF report from bills (Hebrew, RTL)
import os
from fpdf import FPDF
from io import BytesIO

try:
    from bidi.algorithm import get_display
    BIDI_OK = True
except Exception:
    BIDI_OK = False


def rtl(text):
    # flip Hebrew so it reads right-to-left in the PDF
    if not BIDI_OK:
        return str(text)
    return get_display(str(text))


def _find_font():
    # try a few common Hebrew-capable TTF locations
    candidates_reg = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/David.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Davidbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ]
    reg = next((p for p in candidates_reg if os.path.exists(p)), None)
    bold = next((p for p in candidates_bold if os.path.exists(p)), None)
    return reg, bold


def build_report_pdf(user_name, bills, totals_by_cat):
    pdf = FPDF()
    pdf.add_page()

    reg, bold = _find_font()
    if reg:
        pdf.add_font("Body", "", reg, uni=True)
        if bold:
            pdf.add_font("Body", "B", bold, uni=True)
        else:
            pdf.add_font("Body", "B", reg, uni=True)
        font_main = "Body"
    else:
        font_main = "Helvetica"

    # title
    pdf.set_font(font_main, "B", 18)
    pdf.cell(0, 12, rtl("BillEase - דוח שנתי"), ln=1, align="C")
    pdf.set_font(font_main, "", 11)
    pdf.cell(0, 8, rtl(f"שם המשתמש: {user_name}"), ln=1, align="R")
    pdf.ln(4)

    # totals by category
    pdf.set_font(font_main, "B", 13)
    pdf.cell(0, 9, rtl("סיכום לפי קטגוריה"), ln=1, align="R")
    pdf.set_font(font_main, "", 11)
    for cat, total in totals_by_cat.items():
        line = f'{cat}: {total:.2f} ש"ח'
        pdf.cell(0, 7, rtl(line), ln=1, align="R")
    pdf.ln(4)

    # bills table
    pdf.set_font(font_main, "B", 13)
    pdf.cell(0, 9, rtl("רשימת חשבונות"), ln=1, align="R")

    # header row
    pdf.set_font(font_main, "B", 10)
    pdf.cell(40, 8, rtl("ספק"), border=1, align="C")
    pdf.cell(25, 8, rtl("סכום"), border=1, align="C")
    pdf.cell(35, 8, rtl("קטגוריה"), border=1, align="C")
    pdf.cell(35, 8, rtl("תאריך פירעון"), border=1, align="C")
    pdf.cell(20, 8, rtl("שולם"), border=1, align="C", ln=1)

    pdf.set_font(font_main, "", 10)
    for b in bills:
        pdf.cell(40, 7, rtl(str(b.get("supplier", ""))[:20]), border=1, align="R")
        pdf.cell(25, 7, f"{float(b['amount']):.2f}", border=1, align="R")
        pdf.cell(35, 7, rtl(str(b.get("category", ""))[:18]), border=1, align="R")
        pdf.cell(35, 7, str(b["due_date"]), border=1, align="C")
        pdf.cell(20, 7, rtl("כן" if b["is_paid"] else "לא"), border=1, align="C", ln=1)

    out = BytesIO()
    pdf.output(out)
    out.seek(0)
    return out
