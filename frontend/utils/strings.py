"""Every piece of interface text, so the language is changed here and nowhere else."""

APP_TITLE = "نظام ولوحة تحكم ذكية لتحليل واستخراج وتعديل المستندات"
APP_CAPTION = "ارفع كشوف الرواتب (PDF وWord وExcel وCSV) ليستخرج النظام بياناتها ويعرضها للمراجعة."

UPLOAD_HEADER = "رفع المستندات"
UPLOAD_LABEL = "اسحب الملفات هنا أو اخترها من جهازك"
UPLOAD_HELP = "الأنواع المقبولة: PDF وDOCX وXLSX وCSV، وبحد أقصى {max_mb} ميغابايت للملف."
UPLOAD_BUTTON = "ابدأ الرفع والمعالجة"
UPLOAD_NONE = "اختر ملفاً واحداً على الأقل."
UPLOAD_OK = "تم رفع «{name}» وبدأت معالجته."
UPLOAD_FAILED = "تعذّر رفع «{name}»: {reason}"

LIST_HEADER = "المستندات"
LIST_EMPTY = "لا توجد مستندات بعد. ارفع أول كشف رواتب."
COLUMN_FILE = "الملف"
COLUMN_TYPE = "النوع"
COLUMN_STATUS = "الحالة"
COLUMN_UPLOADED = "تاريخ الرفع"
COLUMN_ACTIONS = "إجراءات"

STATUS_LABELS = {
    "pending": "بانتظار المعالجة",
    "processing": "قيد المعالجة",
    "completed": "اكتملت المعالجة",
    "failed": "فشلت المعالجة",
}
STATUS_COLORS = {"pending": "gray", "processing": "blue", "completed": "green", "failed": "red"}

DELETE = "حذف"
DELETE_NOTE = "يُحذف المستند مع ملفه الأصلي وكل حقوله المستخرجة، ولا يمكن التراجع."
DELETE_CONFIRM = "تأكيد الحذف"
DELETE_DONE = "حُذف «{name}»."
DELETE_FAILED = "تعذّر حذف «{name}»: {reason}"

NAV_HOME = "المستندات"
NAV_DETAILS = "تفاصيل المستند"
NAV_ANALYTICS = "التحليلات"
DETAILS_BUTTON = "التفاصيل"

DETAILS_NO_ID = "لم يُحدد مستند. افتح مستنداً من قائمة المستندات."
DETAILS_NOT_FOUND = "المستند غير موجود. ربما حُذف."
DETAILS_NOT_READY = "لم تكتمل معالجة هذا المستند بعد. الحالة: {status}."
DETAILS_INFO = "{type} - {size} - رُفع في {when}"

FIELDS_HEADER = "الحقول المستخرجة"
FIELDS_HELP = "عدّل أي قيمة في عمود «القيمة» ثم اضغط حفظ التعديلات. الحقول التي لم تُوجد في المستند أو لا تتسق حساباتها تُعلَّم بأنها تحتاج مراجعة."
FIELDS_EMPTY = "لا توجد حقول مستخرجة لهذا المستند."
FILTER_REVIEW = "الحقول التي تحتاج مراجعة فقط"
FILTER_REVIEW_EMPTY = "لا توجد حقول تحتاج مراجعة."
COLUMN_RECORD = "الموظف"
COLUMN_FIELD = "الحقل"
COLUMN_ORIGINAL = "المستخرج"
COLUMN_VALUE = "القيمة"
COLUMN_CONFIDENCE = "الثقة"
COLUMN_NOTE = "ملاحظة"
NOTE_REVIEW = "تحتاج مراجعة"
NOTE_CORRECTED = "مصحَّحة"
RECORD_FALLBACK = "سجل {number}"
FIELD_LABELS = {
    "employee_name": "اسم الموظف",
    "employee_id": "الرقم الوظيفي",
    "period": "الفترة",
    "basic_salary": "الراتب الأساسي",
    "allowances": "البدلات",
    "deductions": "الاستقطاعات",
    "net_salary": "صافي الراتب",
    "currency": "العملة",
}
SAVE = "حفظ التعديلات"
SAVE_NONE = "لا توجد تعديلات للحفظ."
SAVE_DONE = "حُفظ {count} تعديل."
SAVE_FAILED = "تعذّر حفظ «{field}» للموظف «{record}»: {reason}"

KPI_RECORDS = "عدد الموظفين"
KPI_TOTAL_NET = "مجموع صافي الرواتب"
KPI_CONFIDENCE = "متوسط الثقة"
KPI_REVIEW = "حقول تحتاج مراجعة"
CHARTS_HEADER = "الرسوم البيانية"
CHART_COMPONENTS = "مكونات الراتب لكل موظف"
CHART_LIMIT = "يعرض الرسم أول {count} موظفاً من {total}."
CHART_EMPTY = "لا أرقام كافية لرسم بياني."
CHART_SERIES = {"basic_salary": "الراتب الأساسي", "allowances": "البدلات", "deductions": "الاستقطاعات"}

EXPORT_HEADER = "التصدير"
EXPORT_NOTE = "يُنشأ ملف جديد بصيغة الأصل ({format}) وبالقيم المصححة، ويبقى الملف الأصلي كما هو."
EXPORT_PDF_NOTE = "تصدير PDF بأفضل جهد: تُستبدل القيم في مواضعها، وقد يصغر الخط ليناسب المساحة."
EXPORT_PREPARE = "تجهيز ملف {format}"
EXPORT_DOWNLOAD = "تنزيل الملف"
EXPORT_READY = "الملف جاهز للتنزيل."
EXPORT_UNPLACED = "لم يُعثر على موضع {count} تصحيحاً في الملف فلم يُطبَّق: {fields}. عدّلها في الملف المصدَّر يدوياً."
EXPORT_FAILED = "تعذّر التصدير: {reason}"

PAGE_PREVIOUS = "السابق"
PAGE_NEXT = "التالي"
PAGE_OF = "صفحة {page} من {pages}"
TOTAL = "{total} مستند"

ERROR_NO_KEY = "لم يُضبط مفتاح الوصول. عيّن المتغير API_KEY في بيئة الواجهة (انظر .env.example)."
ERROR_UNREACHABLE = "تعذّر الاتصال بالخدمة الخلفية على {url}. تأكد من تشغيلها."
ERROR_REJECTED_KEY = "رفضت الخدمة الخلفية مفتاح الوصول. تأكد أن API_KEY متطابق في الخدمتين."
ERROR_GENERIC = "خطأ من الخدمة الخلفية ({status}): {reason}"

ANALYTICS_TITLE = "التحليلات العامة"
ANALYTICS_CAPTION = "ملخص عبر كل المستندات، وما تعلّمه النظام من تصحيحاتك."
ANALYTICS_EMPTY = "لا توجد مستندات بعد، فلا ملخص يُعرض. ارفع أول كشف رواتب."
KPI_DOCUMENTS = "عدد المستندات"
KPI_COMPLETED = "مستندات اكتملت معالجتها"
KPI_FIELDS = "عدد الحقول المستخرجة"
KPI_CORRECTIONS = "عدد التصحيحات"
KPI_NO_CONFIDENCE = "-"
CHART_BY_TYPE = "المستندات حسب النوع"
CHART_BY_STATUS = "المستندات حسب الحالة"
CHART_BY_FIELD = "التصحيحات حسب الحقل"
CHART_CONFIDENCE = "متوسط الثقة في كل الحقول"
CORRECTIONS_HEADER = "آخر التصحيحات"
CORRECTIONS_HELP = "كل تصحيح يُحفظ مثالاً، وتُعرض الأقرب منها على النموذج عند معالجة المستندات التالية."
CORRECTIONS_EMPTY = "لم تُصحَّح أي قيمة بعد."
COLUMN_BEFORE = "المستخرج"
COLUMN_AFTER = "بعد التصحيح"
COLUMN_DATE = "تاريخ التصحيح"
COLUMN_DOCUMENT = "المستند"

# ---------------------------------------------------------------------- Yahya Intelligent Office System
YAHYA_TITLE = "نظام يحيى الذكي للإدارة — جامعة الطائف"
YAHYA_CAPTION = "بوابة حوكمة وقيد المعاملات، الفرز الذكي والتحقق من سوابق القضايا، والتتبع الهرمي لسجل الموظف."
TAB_INTAKE = "تقييم وقيد المعاملات"
TAB_SEARCH = "البحث الهرمي وسجل المعاملات"
TAB_EXPORT = "تصدير المزامنة والتدقيق"

DECISION_LABELS = {
    "NO_MATCH": "معاملة جديدة كلياً (آمنة للقيد الفوري)",
    "SIMILAR_FOUND": "تم العثور على معاملات مشابهة (يتطلب مراجعة مسؤول الموارد البشرية)",
    "SAME_PERSON_NEW_TOPIC": "موظف مسجل مسبقاً بموضوع أو دعوى مستقلة (قيد معاملة جديدة لنفس الموظف)",
}
PRIORITY_LABELS = {
    "P1": "أولوية قصوى P1 (مهلة نظامية 5 أيام عمل أو أقل)",
    "P2": "أولوية عادية P2",
    "P3": "أولوية منخفضة P3",
}
CASE_STATUS_LABELS = {
    "NEW": "جديدة",
    "ANL": "قيد الدراسة والتحليل",
    "WAI": "بانتظار الإفادة",
    "RDY": "جاهزة للقرار",
    "CLS": "مغلقة",
    "HLD": "معلقة",
}

