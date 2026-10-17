# guess a category from the supplier name using keyword rules

SUPPLIER_RULES = [
    # electricity
    (["חשמל", "electric"], "חשמל"),
    # water
    (["מים", "תאגיד מים", "מי "], "מים"),
    # internet
    (["בזק", "hot", "אינטרנט", "סלקום אינטרנט", "פרטנר tv"], "אינטרנט"),
    # phone / cell
    (["סלקום", "פלאפון", "פרטנר", "we4g", "012", "phone", "טלפון"], "טלפון"),
    # rent / mortgage
    (["שכירות", "שכר דירה", "משכנתא"], "שכירות"),
    # food / supermarkets
    (["שופרסל", "רמי לוי", "ויקטורי", "מגה", "יוחננוף", "סופר"], "מזון"),
    # insurance
    (["הראל", "מנורה", "כלל", "הפניקס", "מגדל", "ביטוח"], "ביטוח"),
    # subscriptions
    (["netflix", "spotify", "youtube", "disney", "מנוי"], "מנויים"),
    # city tax
    (["עירייה", "ארנונה"], "ארנונה"),
]


def guess_category(supplier):
    if not supplier:
        return None
    s = supplier.lower()
    for keywords, cat in SUPPLIER_RULES:
        for k in keywords:
            if k.lower() in s:
                return cat
    return None
