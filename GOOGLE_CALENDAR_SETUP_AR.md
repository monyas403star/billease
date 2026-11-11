# ربط BillEase بتقويم Google

هذه إضافة مبنية على نسخة GitHub ذات المعرّف 61bf2547ba64e6b9af6c9c6df3592f7580b340df.
لا ترفع ملف ZIP نفسه إلى GitHub: فك الضغط، ثم ضع الملفات في نفس المسارات الموجودة داخله.
احتفظ بنسخة من قاعدة البيانات قبل النشر. لا تستبدل database.db ولا تغيّر مسار القرص الدائم.

## ما الذي يحصل للزبون؟

من صفحة التقويم يضغط «ربط Google Calendar» مرة واحدة، ويختار حساب Google ويوافق على مشاركة تفاصيل الفواتير.
ينشئ BillEase تقويمًا مستقلاً اسمه BillEase داخل Google. جميع الفواتير المحفوظة والأقساط تُضاف بأيام استحقاقها.
حفظ فاتورة أو تعليمها كمدفوعة أو حذفها يضع التغيير في طابور دائم ضمن نفس معاملة SQLite تلقائيًا.
عامل بالخلفية يرسل التغييرات ويعيد المحاولة عند عطل الشبكة. لا يلزم الضغط لإضافة كل فاتورة.
الموعد حدث ليوم كامل، ولا نفترض ساعة دفع. تنبيهات Google ليست مفعّلة تلقائيًا؛ إشعارات البريد الحالية مستقلة.
لا يتم دفع أي مبلغ عبر هذا الربط.

## 1 — Google Cloud

1. افتحي https://console.cloud.google.com/ بحساب صاحبات المشروع.
2. من اختيار المشروع أعلى الصفحة: New Project. الاسم BillEase. ثم Create واختاري المشروع.
3. افتحي APIs & Services ثم Library. ابحثي عن Google Calendar API واضغطي Enable.
4. افتحي Google Auth platform ثم Branding ثم Get Started إذا ظهر.
5. اسم التطبيق BillEase، بريد الدعم بريدكن، ونوع الجمهور External، وبريد الاتصال بريدكن.
6. من Audience اتركي Testing للتجربة وأضيفي بريدك وبريد زميلاتك إلى Test users.
7. من Data Access أضيفي هذه الصلاحية وحدها:

   https://www.googleapis.com/auth/calendar.app.created

8. من Clients اضغطي Create client. النوع Web application. الاسم BillEase Web.
9. في Authorized redirect URIs أضيفي العنوان التالي حرفيًا، بدون شرطة مائلة إضافية:

   https://billease-0ycc.onrender.com/oauth/google/calendar/callback

10. احفظي Client ID وClient secret. لا تضعي السر في GitHub أو في JavaScript أو في صور عامة.

هذه الصلاحية تُستخدم لإنشاء تقويم ثانوي وإدارة أحداث التقويمات التي ينشئها التطبيق؛ لا نطلب قراءة مواعيد المستخدم الشخصية.
في وضع Testing قد تنتهي صلاحية الربط بعد 7 أيام؛ قبل إتاحته للزبائن انتقلي إلى إعداد النشر المناسب في Google واستكملي متطلبات شاشة الموافقة والسياسات والتحقق التي تظهر في لوحة المشروع. لا نعدّ وضع التجربة إطلاقًا عامًا.

## 2 — رفع الملفات

ارفعي ملفات التعديل في مساراتها الحالية دفعة واحدة قدر الإمكان:

- app.py
- google_calendar_sync.py (ملف جديد في جذر المشروع)
- requirements.txt
- translations.json
- templates/calendar.html
- static/js/google_calendar.js (ملف جديد)
- tests/test_google_calendar_sync.py (اختبارات)
- GOOGLE_CALENDAR_SETUP_AR.md (هذا الدليل)

لا ترفعي مفاتيح أو قاعدة بيانات أو مجلد __pycache__. لا تنقلي الملفات الموجودة تحت static أو templates إلى جذر المشروع.
وجود الملفات بدون متغيرات Google لا يفعّل الربط؛ ستظهر رسالة أن الإعداد لم يكتمل.

## 3 — Render

في خدمة BillEase افتحي Environment وأضيفي:

| الاسم | القيمة |
|---|---|
| GOOGLE_CLIENT_ID | Client ID من Google |
| GOOGLE_CLIENT_SECRET | Client secret من Google |
| GOOGLE_REDIRECT_URI | https://billease-0ycc.onrender.com/oauth/google/calendar/callback |
| CALENDAR_TOKEN_KEY | مفتاح Fernet خاص يُولّد بالأمر أدناه |

بعد تثبيت المتطلبات، ولّدي المفتاح من Render Shell أو من بيئة Python موثوقة فيها cryptography:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

انسخي الناتج إلى CALENDAR_TOKEN_KEY. لا تضعي هذا المفتاح في الكود ولا تغيّريه بعد ربط المستخدمين؛ تغييره دون ترحيل التشفير يمنع فك رموز الربط المحفوظة.
احتفظي به مع أسرار الخدمة. اتركي CALENDAR_BACKGROUND على القيمة الافتراضية 1. لا يلزم Cron لهذه الإضافة.
احفظي المتغيرات وانشري آخر commit. يجب أن يعمل السيرفر لتعمل المزامنة؛ عند توقفه تبقى التغييرات محفوظة وتستأنف بعد تشغيله.
تنشأ جداول الإضافة تلقائيًا دون حذف الجداول الحالية. رموز الوصول الطويلة مشفرة داخل SQLite.

## 4 — تجربة حقيقية قبل العرض

1. افتحي الموقع وسجلي الدخول بحسابك.
2. افتحي صفحة التقويم، واضغطي ربط Google Calendar.
3. اختاري بريدًا موجودًا ضمن Test users ثم وافقي. لا تحتاجين تسجيل الدخول إلى BillEase بواسطة Google؛ هذا تفويض منفصل للتقويم.
4. انتظري ظهور حالة نجاح المزامنة. افتحي https://calendar.google.com بنفس البريد واختاري عرض تقويم BillEase.
5. احفظي فاتورة تجريبية بتاريخ معروف، وتحققي من ظهورها مرة واحدة وبالمبلغ الصحيح.
6. جرّبي فاتورة بأقساط: يظهر كل قسط محفوظ بموعده، وليس حدثًا واحدًا بالمبلغ الإجمالي.
7. علّمي الفاتورة كمدفوعة: يتغيّر عنوان الحدث ولونه. احذفي الفاتورة التجريبية: يُحذف الحدث.
8. اختبري حساب BillEase آخر بحساب Google آخر، وتحققي من فصل البيانات.

المزامنة إرسال تلقائي وليست ضمانًا للظهور في نفس الثانية. حالة «تمت المزامنة» تعني أن Google قبل التغييرات؛ ظهورها على الجهاز يعتمد أيضًا على الإنترنت ومزامنة تطبيق التقويم.
إذا اخترتِ الحساب نفسه لزبونين مختلفين، سينشأ تقويم BillEase منفصل لكل ربط.

## 5 — التلفون والكمبيوتر

على الكمبيوتر افتحي Google Calendar بالحساب الذي وافق على الربط، وفعّلي عرض تقويم BillEase.
على Samsung يمكن استخدام تطبيق Google Calendar بالحساب نفسه وتفعيل تقويم BillEase. تطبيق Samsung Calendar يحتاج تفعيل مزامنة Google Calendars وعرض تقويم BillEase ضمن تقاويم الحساب.
على iPhone يمكن استخدام Google Calendar، أو إضافة حساب Google إلى إعدادات تقويم Apple وتفعيل Calendars ثم اختيار تقويم BillEase للعرض.
الربط مع حساب Google؛ لا يعني كتابة مباشرة إلى حساب iCloud أو Outlook منفصل. الجهاز الذي لا يحمل نفس حساب Google لن تظهر عليه البيانات تلقائيًا.

## حدود وسلوك متعمد

- التحديث باتجاه واحد من BillEase إلى Google. تعديل حدث في Google لا يعدّل الفاتورة في الموقع.
- لا نضيف دفعات مستقبلية غير موجودة بقاعدة البيانات. الفاتورة المتكررة تنشئ دفعتها التالية حسب منطق الموقع الحالي.
- إلغاء الربط يزيل الرموز من BillEase ويطلب إلغاء التفويض في Google، لكنه لا يحذف أحداث المستخدم السابقة. احذفي التقويم القديم من Google قبل إعادة الربط حتى لا يظهر تقويمان. إذا فشل إلغاء تفويض Google تظهر رسالة لإزالته من أذونات الحساب أيضًا.
- لا نطلب صلاحيات الوصول إلى بقية التقويمات؛ لا نقرأها ولا نعدّلها.
- قد يلزم إعادة الربط إذا سحب المستخدم التفويض أو انتهت صلاحيته أو حذف تقويم BillEase من Google.
- تجنّبي تسجيل query string لمسار OAuth callback في إعدادات access logs؛ يحتوي كود تفويض قصير العمر. الإضافة لا تطبع الرموز أو محتوى الفواتير في السجلات.
- إنشاء تقويم Google ليس معاملة مشتركة مع SQLite؛ إذا توقف السيرفر مباشرة بعد إنشاء التقويم وقبل حفظ الربط فقد يبقى تقويم فارغ في Google. يمكن حذفه يدويًا وإعادة الربط.

## الاختبارات المنفذة

```sh
python -m unittest discover -s tests -p test_google_calendar_sync.py -v
```

10 اختبارات ناجحة محليًا، بردود Google محاكية: الحالة دون دخول، فصل الحسابات، state وPKCE، التشفير، دورة الإضافة والدفع والحذف، منع تكرار الأحداث، إعادة المحاولة، قفل العامل والدفعات، فصل الربط، وعرض الواجهة بثلاث لغات.
لم يتم الاتصال بحساب Google حقيقي أثناء التطوير. يجب تنفيذ تجربة الخطوة 4 بعد إعداد المفاتيح.

## المراجع الرسمية

- https://developers.google.com/workspace/guides/configure-oauth-consent
- https://developers.google.com/workspace/calendar/api/auth
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/protocols/oauth2
- https://developers.google.com/workspace/calendar/api/v3/reference/calendars/insert
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
