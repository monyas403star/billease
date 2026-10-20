"""Bill OCR. Extract candidates; never invent missing dates or amounts."""
import logging
import math
import re
import shutil
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)
try:
    import pytesseract
    from PIL import Image, ImageOps
    OCR_OK = shutil.which("tesseract") is not None
except ImportError:
    OCR_OK = False

DATE_LABELS = ["לתשלום עד תאריך", "לתשלום עד", "מועד תשלום", "תאריך אחרון לתשלום",
               "תאריך פירעון", "due date", "pay by", "payment deadline",
               "تاريخ الاستحقاق", "موعد الدفع", "آخر موعد للدفع"]
TOTAL_LABELS = ['סה"כ לתשלום', 'סך הכל לתשלום', 'סכום לתשלום',
                'total amount due', 'total due', 'grand total',
                'المبلغ المستحق', 'المجموع للدفع', 'اجمالي المبلغ']
DEBT_LABELS = ['יתרת חוב', 'ללא החשבון הנוכחי', 'previous balance', 'arrears',
               'رصيد سابق', 'متأخرات']
RECEIPT_TOTAL_LABELS = ['סה"כ תקבולים', 'סך התקבולים', 'תקבולים', 'receipt total', 'total received']


def _is_receipt(text):
    header = '\n'.join(normalize_text(text).splitlines()[:40])
    return bool(re.search(
        r'תאריך\s*הקבלה|^\s*קבלה(?:\s*[:#-]?\s*\d|\s*$)|'
        r'^\s*receipt(?:\s+(?:no|number|total)\b|\s*[:#]?\s*\d|\s*$)|'
        r'tax invoice\s*/\s*receipt', header, re.I | re.M))


PERIOD_LABELS = ['תאריך הדפסה', 'תאריך הפקה', 'תקופת החשבון', 'תאריך קריאה',
                 'issue date', 'billing period', 'تاريخ الاصدار', 'فترة الاستهلاك']


def normalize_text(text):
    result = []
    for char in str(text):
        if unicodedata.category(char) == 'Cf':
            continue
        try:
            char = str(unicodedata.decimal(char))
        except (ValueError, TypeError):
            pass
        result.append(char)
    return ''.join(result).replace('٫', '.').replace('٬', ',').replace('\u00a0', ' ')


def _compact(text):
    return ''.join(c.lower() for c in text if c.isalpha())


def _labels(text, phrases):
    lines = [(m.start(), m.end(), m.group()) for m in re.finditer(r'[^\n]+', text)
             if _compact(m.group())]
    found = []
    for i, (start, end, line) in enumerate(lines):
        for count in (1, 2):
            group = lines[i:i + count]
            if len(group) != count or group[-1][1] - start > 150:
                continue
            segment = text[start:group[-1][1]]
            letters = [(c.lower(), start + j) for j, c in enumerate(segment) if c.isalpha()]
            compact = ''.join(c for c, _ in letters)
            for phrase in phrases:
                target = _compact(phrase)
                best = (0, 0, 0)
                exact = compact.find(target)
                if exact >= 0:
                    best = (1.0, exact, exact + len(target))
                else:
                    for length in (len(target) - 1, len(target), len(target) + 1):
                        for j in range(max(0, len(compact) - length + 1)):
                            value = compact[j:j + length]
                            if phrases is DATE_LABELS:
                                if any('א' <= c <= 'ת' for c in target):
                                    anchors = [w for w in ('עד', 'תאריך', 'מועד', 'פירעון') if w in target]
                                    if not any(w in value for w in anchors):
                                        continue
                                elif any('ا' <= c <= 'ي' for c in target):
                                    if not any(w in value for w in ('تاريخ', 'موعد', 'استحقاق')):
                                        continue
                                elif not any(w in value for w in ('due', 'payby', 'deadline')):
                                    continue
                            ratio = SequenceMatcher(None, value, target).ratio()
                            if ratio > best[0]:
                                best = (ratio, j, j + length)
                similarity, left, right = best
                if similarity >= 0.84 and right > left:
                    found.append((letters[left][1], letters[right - 1][1] + 1, similarity))
    return found


def _near(start, end, labels, radius=160):
    score = 0.0
    for left, right, similarity in labels:
        distance = max(left - end, start - right, 0)
        if distance <= radius:
            score = max(score, similarity * (1 - distance / (radius + 1)))
    return score


def _dates(text):
    text = normalize_text(text)
    positive = _labels(text, DATE_LABELS)
    negative = _labels(text, PERIOD_LABELS)
    patterns = [
        (r'(?<![\d/.-])(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})(?![\d/.-])', True),
        (r'(?<![\d/.-])(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4}|\d{2})(?![\d/.-])', False),
    ]
    found = []
    for pattern, year_first in patterns:
        for match in re.finditer(pattern, text):
            a, b, c = map(int, match.groups())
            year, month, day = (a, b, c) if year_first else (c, b, a)
            if year < 100:
                year += 2000
            if not 1900 <= year <= 2199:
                continue
            try:
                value = datetime(year, month, day).date().isoformat()
            except ValueError:
                continue
            pos = _near(match.start(), match.end(), positive)
            neg = _near(match.start(), match.end(), negative, 70)
            found.append((value, pos - 0.65 * neg, pos))
    return found


def _amounts(text):
    text = normalize_text(text)
    # Replace date spans with spaces so label positions stay unchanged.
    text = re.sub(r'\b\d{1,4}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,4}\b',
                  lambda m: ' ' * len(m.group()), text)
    positive = _labels(text, (RECEIPT_TOTAL_LABELS if _is_receipt(text) else TOTAL_LABELS))
    negative = _labels(text, DEBT_LABELS)
    pattern = r'(?<![\d.,])(?:\d{1,3}(?:,\d{3})+\.\d{2}|\d+[.,]\d{2})(?![\d.,])'
    found = []
    for match in re.finditer(pattern, text):
        raw = match.group()
        raw = raw.replace(',', '') if ',' in raw and '.' in raw else raw.replace(',', '.')
        value = float(raw)
        if value <= 0:
            continue
        pos = _near(match.start(), match.end(), positive)
        if _is_receipt(text):
            left = text.rfind('\n', 0, match.start()) + 1
            right = text.find('\n', match.end())
            line = text[left:right if right >= 0 else len(text)]
            if _labels(line, TOTAL_LABELS) and not _labels(line, RECEIPT_TOTAL_LABELS):
                pos = 0
        neg = _near(match.start(), match.end(), negative)
        score = pos if pos > neg + .04 else pos - 1.5 * neg
        found.append((value, score, pos))
    return found


def _choose(texts, extractor):
    best = {}
    for text in texts:
        for value, score, positive in extractor(text):
            if positive < 0.45 or score < 0.35:
                continue
            best[value] = max(score, best.get(value, -10))
    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return None
    # Close, conflicting candidates require human review.
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < 0.08:
        return None
    return ranked[0][0]


def find_amount(text):
    return _choose([text], _amounts)


def find_date(text):
    if _is_receipt(text):
        return None
    return _choose([text], _dates)


def find_supplier(text):
    # Compare header text across OCR views rather than returning a page number.
    views = normalize_text(text).split('\n\n')
    lines = [line.strip() for view in views for line in view.splitlines()[:18] if line.strip()]
    for line in lines:
        legal = re.search(r"([א-ת][א-ת \"״'-]{3,70}בע\s*[\"״']?\s*מ)\b", line)
        if legal and not re.search(r'לכבוד|מען|כתובת|מספר', legal.group(1)):
            return legal.group(1).strip()[:50]
    for line in lines:
        if re.fullmatch(r"(?:מי|مياه|חברת|شركة)\s+[א-תا-ي \"״'-]{2,40}", line):
            return line[:50]
    header = '\n'.join(lines)
    websites = re.findall(r'(?:https?://|www\.)\s*(?:www\.)?([a-z0-9][a-z0-9-]{2,})\.[a-z]{2,}(?:\.[a-z]{2,})?', header, re.I)
    for name in websites:
        if name.lower() not in {'gmail', 'outlook', 'hotmail', 'yahoo', 'icloud', 'google', 'facebook'}:
            return name[:50]
    for line in lines:
        if re.search(r"בע[\"״']?מ|\b(?:ltd|limited|inc|llc)\b", line, re.I):
            if len(_compact(line)) >= 7 and not re.search(r'מען|לכבוד|טלפון|כתובת|address|phone', line, re.I):
                return line[:50]
    # A weak or conflicting header should be reviewed, not filled with gibberish.
    return None

def _read_view(view, languages, timeout, offset_x, psm=11):
    data = pytesseract.image_to_data(
        view, lang=languages, config=f'--psm {psm}', timeout=timeout,
        output_type=pytesseract.Output.DICT,
    )
    groups = {}
    for i, word in enumerate(data['text']):
        if not word.strip():
            continue
        key = tuple(data[k][i] for k in ('page_num', 'block_num', 'par_num', 'line_num'))
        groups.setdefault(key, []).append(i)
    records = []
    for indices in groups.values():
        left = min(data['left'][i] for i in indices)
        top = min(data['top'][i] for i in indices)
        right = max(data['left'][i] + data['width'][i] for i in indices)
        bottom = max(data['top'][i] + data['height'][i] for i in indices)
        records.append({
            'text': normalize_text(' '.join(data['text'][i] for i in indices)),
            'box': (left + offset_x, top, right + offset_x, bottom),
        })
    return records


def _spatial_choose(records, kind, width, height):
    receipt = _is_receipt('\n'.join(r['text'] for r in records))
    phrases = DATE_LABELS if kind == 'date' else (RECEIPT_TOTAL_LABELS if receipt else TOTAL_LABELS)
    extractor = _dates if kind == 'date' else _amounts
    positives = [(r, max((x[2] for x in _labels(r['text'], phrases)), default=0)) for r in records]
    positives = [(r, quality) for r, quality in positives if quality >= .84]
    negatives_phrases = PERIOD_LABELS if kind == 'date' else DEBT_LABELS
    negatives = [r for r in records if _labels(r['text'], negatives_phrases)]
    best = {}
    for record in records:
        candidates = extractor(record['text'])
        if not candidates:
            continue
        x1, y1, x2, y2 = record['box']
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        for value, _, _ in candidates:
            score = 0
            for label, quality in positives:
                a, b, c, d = label['box']
                # Prefer labels immediately above/below the value in its column.
                gap_x = max(a - x2, x1 - c, 0) / width
                gap_y = max(b - y2, y1 - d, 0) / height
                center_x = abs(cx - (a + c) / 2) / width
                if gap_x > .12 or gap_y > .10 or center_x > .25:
                    continue
                candidate_score = quality - 4 * gap_y - 1.5 * center_x - 2 * gap_x
                score = max(score, candidate_score)
            for label in negatives:
                a, b, c, d = label['box']
                gap_y = max(b - y2, y1 - d, 0) / height
                gap_x = max(a - x2, x1 - c, 0) / width
                if gap_y < .025 and gap_x < .06:
                    score -= .65
            if score >= .5:
                best[value] = max(best.get(value, -10), score)
    ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)
    if not ranked or (len(ranked) > 1 and ranked[0][1] - ranked[1][1] < .08):
        return None
    return ranked[0][0]


def scan_bill(image_path):
    result = dict(amount=None, due_date=None, supplier=None, text='', error=None, notice=None, document_type='unknown')
    if not OCR_OK:
        result['error'] = 'OCR engine is not installed'
        logger.error('[OCR] engine is not installed')
        return result
    texts = []
    records = []
    failures = 0
    deadline = time.monotonic() + 65
    try:
        with Image.open(image_path) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
        longest = max(image.size)
        scale = min(4, max(1, math.ceil(2400 / longest))) if longest < 2400 else min(1, 2800 / longest)
        image = image.resize((max(1, round(image.width * scale)),
                              max(1, round(image.height * scale))), Image.Resampling.BICUBIC)
        image = ImageOps.autocontrast(ImageOps.grayscale(image))
        # Overlapping columns handle bills with side panels and tables.
        views = [image, image.crop((0, 0, round(image.width * .6), image.height)),
                 image.crop((round(image.width * .4), 0, image.width, image.height))]
        jobs = [(views[0], 'heb+eng', 0, 6), (views[0], 'heb+ara+eng', 0, 11),
                (views[1], 'heb+ara+eng', 0, 11),
                (views[2], 'heb+ara+eng', round(image.width * .4), 11)]
        for view, languages, offset, psm in jobs:
            remaining = deadline - time.monotonic()
            if remaining < 1:
                break
            try:
                lines = _read_view(view, languages, min(15, remaining), offset, psm=psm)
                records.extend(lines)
                text = '\n'.join(line['text'] for line in lines)
                if text.strip():
                    texts.append(text)
            except (RuntimeError, pytesseract.TesseractError) as exc:
                failures += 1
                logger.warning('[OCR] a pass failed: %s', type(exc).__name__)
        result['text'] = '\n\n'.join(texts)
        if not texts:
            result['error'] = 'Image scanning failed' if failures else 'No readable text found'
            return result
        result['supplier'] = find_supplier(result['text'])
        result['amount'] = _spatial_choose(records, 'amount', image.width, image.height)
        receipt = _is_receipt(result['text'])
        result['document_type'] = 'receipt' if receipt else 'invoice'
        result['due_date'] = None if receipt else _spatial_choose(records, 'date', image.width, image.height)
        if receipt:
            result['notice'] = ('זוהתה קבלה. הסכום הוא סך המסמך ולא בהכרח חוב פתוח. '
                                'אין מועד תשלום יחיד מאומת; בחרו תאריך ידנית ובדקו אם כבר שולם.')
        elif longest < 1000:
            result['notice'] = 'התמונה קטנה. מומלץ צילום מקורי חד יותר; בדקו את הסכום והתאריך לפני השמירה.'
        # Do not put invoice text, identities, or account numbers in server logs.
        logger.info('[OCR] fields: amount=%s due_date=%s',
                    result['amount'] is not None, result['due_date'] is not None)
    except Exception as exc:
        result['error'] = 'Image scanning failed'
        logger.error('[OCR] scanning failed: %s', type(exc).__name__)
    return result