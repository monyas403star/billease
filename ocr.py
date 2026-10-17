# tries to read a bill image and pull amount + date
import re
from datetime import datetime

try:
    import pytesseract
    from PIL import Image
    OCR_OK = True
except Exception:
    OCR_OK = False


def scan_bill(image_path):
    # returns a dict with amount, due_date, supplier (best guess)
    result = {"amount": None, "due_date": None, "supplier": None, "text": ""}
    if not OCR_OK:
        return result
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        result["text"] = text
        result["amount"] = find_amount(text)
        result["due_date"] = find_date(text)
        result["supplier"] = find_supplier(text)
    except Exception:
        pass
    return result


def find_amount(text):
    # grab the biggest number that looks like money
    matches = re.findall(r"(\d+[\.,]\d{2})", text)
    if not matches:
        return None
    nums = []
    for m in matches:
        try:
            nums.append(float(m.replace(",", ".")))
        except ValueError:
            pass
    if not nums:
        return None
    return max(nums)


def find_date(text):
    # look for dd/mm/yyyy or yyyy-mm-dd
    patterns = [
        r"(\d{2}/\d{2}/\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{2}-\d{2}-\d{4})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            raw = m.group(1)
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
    return None


def find_supplier(text):
    # first non-empty line, trimmed
    for line in text.splitlines():
        clean = line.strip()
        if len(clean) > 2:
            return clean[:50]
    return None
