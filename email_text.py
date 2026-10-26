"""Email copy uses the recipient's account language, including background jobs."""
def welcome(locale, name):
    return {
        'he': ('ברוך הבא ל-BillEase', f'שלום {name}, החשבון שלך מוכן לשימוש!'),
        'ar': ('أهلاً بك في BillEase', f'مرحباً {name}، حسابك جاهز للاستخدام!'),
        'en': ('Welcome to BillEase', f'Hello {name}, your account is ready!'),
    }.get(locale, ('ברוך הבא ל-BillEase', f'שלום {name}, החשבון שלך מוכן לשימוש!'))


def recovery(locale, code):
    return {
        'he': ('איפוס סיסמה ל-BillEase', f'קוד החד-פעמי שלך: {code}\nתוקפו 10 דקות.'),
        'ar': ('إعادة تعيين كلمة مرور BillEase', f'رمزك لمرة واحدة: {code}\nصالح لمدة 10 دقائق.'),
        'en': ('Reset your BillEase password', f'Your one-time code: {code}\nValid for 10 minutes.'),
    }.get(locale, ('BillEase', code))


def bill(locale, kind, name, supplier, amount, due):
    copies = {
        'he': ('שלום', 'ספק', 'סכום', 'מועד לתשלום', {
            'paid': ('החשבון סומן כשולם', 'זהו אישור רישום במערכת, ולא אישור סליקה מהספק.'),
            'deleted': ('החשבון נמחק', 'המחיקה במערכת אינה תשלום או ביטול חוב אצל הספק.'),
            'seven_days': ('מועד התשלום חל בשבעת הימים הקרובים', 'אם שילמתם, סמנו את החשבון כשולם באתר.'),
            'overdue': ('מועד התשלום עבר והחשבון עדיין פתוח', 'אם שילמתם, עדכנו את מצב החשבון באתר.'),
        }),
        'ar': ('مرحباً', 'المورّد', 'المبلغ', 'موعد الدفع', {
            'paid': ('تم تسجيل الفاتورة كمدفوعة', 'هذا تأكيد تسجيل في الموقع وليس إثبات دفع من المورّد.'),
            'deleted': ('تم حذف الفاتورة', 'الحذف من الموقع لا يعني تسديد الدين أو إلغاءه لدى المورّد.'),
            'seven_days': ('موعد الدفع خلال الأيام السبعة القادمة', 'إذا دفعت، سجّل الفاتورة كمدفوعة في الموقع.'),
            'overdue': ('تجاوزت الفاتورة موعد الدفع وما زالت مفتوحة', 'إذا دفعت، حدّث حالة الفاتورة في الموقع.'),
        }),
        'en': ('Hello', 'Supplier', 'Amount', 'Payment due', {
            'paid': ('Bill marked as paid', 'This confirms a record in BillEase, not payment processing by the supplier.'),
            'deleted': ('Bill deleted', 'Deleting a bill in BillEase does not pay or cancel a debt with the supplier.'),
            'seven_days': ('Payment due within the next seven days', 'If you have paid, mark the bill as paid on the website.'),
            'overdue': ('Payment overdue and bill still open', 'If you have paid, update the bill status on the website.'),
        }),
    }
    greeting, supplier_label, amount_label, due_label, messages = copies.get(locale, copies['he'])
    title, note = messages[kind]
    return f'BillEase — {title}', (f'{greeting} {name},\n\n{title}\n'
        f'{supplier_label}: {supplier}\n{amount_label}: {amount} ILS\n{due_label}: {due}\n\n{note}')
