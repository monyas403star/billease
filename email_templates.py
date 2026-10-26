"""Plain-text localized email content; preference comes from the account, not a browser cookie."""
from i18n import translate_in


def welcome(locale, name):
    return (translate_in(locale, 'ברוך הבא ל-BillEase'),
            translate_in(locale, 'שלום {name}, החשבון שלך מוכן לשימוש!', name=name))


def recovery(locale, code):
    return (translate_in(locale, 'איפוס סיסמה ל-BillEase'),
            translate_in(locale, 'קוד החד-פעמי שלך: {code}\nתוקפו 10 דקות.', code=code))


def bill_event(kind, locale, snapshot):
    t = lambda source, **values: translate_in(locale, source, **values)
    subject, message, footer = {
        'paid': ('BillEase — החשבון סומן כשולם', 'החשבון הבא סומן כשולם במערכת BillEase:', 'זהו אישור רישום במערכת, ולא אישור סליקה מהספק.'),
        'deleted': ('BillEase — אישור מחיקת חשבון', 'החשבון הבא נמחק מהחשבון שלך במערכת BillEase:', 'המחיקה במערכת אינה תשלום או ביטול חוב אצל הספק.'),
        'seven_days': ('BillEase — תזכורת: מועד התשלום מתקרב', 'מועד התשלום חל במהלך שבעת הימים הקרובים:', 'אם שילמתם, סמנו את החשבון כשולם באתר.'),
        'overdue': ('BillEase — חשבון באיחור בתשלום', 'מועד התשלום של החשבון הבא עבר והוא עדיין מסומן כפתוח:', 'אם שילמתם, עדכנו את מצב החשבון באתר.'),
    }[kind]
    details = t('ספק: {supplier}\nסכום: {amount} ש״ח\nמועד לתשלום: {due}',
                supplier=snapshot.get('supplier') or t('הספק'), amount=snapshot['amount'], due=snapshot.get('due_text') or t('לא צוין'))
    if snapshot.get('installment_number'):
        details += '\n' + t('תשלום {number} מתוך {count}', number=snapshot['installment_number'], count=snapshot['installment_count'])
    body = t('שלום {name},', name=snapshot.get('full_name') or '') + '\n\n' + t(message) + '\n' + details + '\n\n' + t(footer)
    return t(subject), body
