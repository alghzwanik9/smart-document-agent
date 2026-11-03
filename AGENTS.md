# نظام ولوحة تحكم ذكية لتحليل واستخراج وتعديل المستندات

## ملخص المعمارية

نظام ولوحة تحكم ذكية لتحليل واستخراج وتعديل المستندات: استخراج وتحليل وتعديل المستندات بذكاء مع تعلم تراكمي
بناء نظام تفاعلي ولوحة تحكم (Dashboard) قوية لاستخراج البيانات بدقة عالية من مختلف أنواع الملفات (PDF، Word، Excel)، تحليلها وعرضها بصرياً، مع إمكانية التعديل على الملفات وإعادة تصديرها، ودعم آلية تعلم تراكمي ذاتي لتحسين دقة الاستخراج تلقائياً بناءً على تصحيحات المستخدم.
Stack: Frontend: Streamlit; Backend: FastAPI + Uvicorn; PDF: PyMuPDF (النص وتحويل الصفحات إلى صور) + pdfplumber (الجداول); OCR: Tesseract عبر pytesseract (العربية والإنجليزية); Excel/CSV: openpyxl (قراءة وكتابة بالحفاظ على التنسيق) + pandas (CSV والتحليل); Word: python-docx; Relational DB: SQLite عبر SQLAlchemy; Vector Store: ChromaDB; LLM: واجهة HTTP قابلة للضبط (المزود والنموذج من متغيرات البيئة); Validation: Pydantic; Testing: pytest + httpx; Packaging: Docker Compose
MVP: واجهة مستخدم لرفع المستندات المتعددة (Drag & Drop); عرض فوري للبيانات المستخرجة في جداول تفاعلية قابلة للفرز والفلترة; رسوم بيانية وتصورات إحصائية آلية للبيانات المستخرجة; محرك قراءة واستخراج يدعم PDF (نصوص ومصورة عبر OCR)، Excel (.xlsx, .csv)، و Word (.docx); الاعتماد على مخطط استخراج منظم (Pydantic / Structured JSON Schema); إمكانية تعديل القيم المستخرجة مباشرة من خلال لوحة التحكم (Editable Table / Inline Edit)
Design: تصميم عصري ونظيف مع التركيز على سهولة القراءة والتفاعل. استخدام بطاقات (cards) لتنظيم المحتوى وعناصر واجهة مستخدم واضحة.
Language: اللغة العربية هي الأساس مع دعم اتجاه RTL (من اليمين إلى اليسار). يجب أن تكون الواجهة قابلة للتعريب بسهولة للغات أخرى.

المواصفات الكاملة في `blueprint.md`.

<!-- planning-studio:skills:begin -->
## المهارات

| المهارة | الحزمة | السبب |
| :--- | :--- | :--- |
| smart-document-agent-conventions | custom | يطابق FastAPI، Streamlit: هذه المهارة تحدد الاتفاقيات والمعايير الصارمة لتطوير نظام ولوحة تحكم ذكية لتحليل واستخراج وتعديل المستندات. يجب استخدامها دائمًا عند البدء |
| impeccable | design-craft | يطابق i18n / RTL، Dashboard UI، UI / Visual design، Architecture: Use when the user wants to design, redesign, shape, critique, audit, polish, clarify, distill, harden, optimize, adapt, animate, colorize |
| developing-with-streamlit | python-data | يطابق Streamlit، Dashboard UI، Build quality: **[REQUIRED]** Use for ALL Streamlit tasks: creating, editing, debugging, beautifying, styling, theming, or optimizing Streamlit |
| api-patterns | core | يطابق REST / GraphQL API، UI / Visual design: Use when designing backend APIs — choosing between REST, GraphQL, or tRPC, structuring response envelopes, configuring pagination |
| database-design | python-data | يطابق Database، Planning: Database design principles and decision-making. Schema design, indexing strategy, ORM selection, serverless databases.. Use: When designing |
| emil-break-ui | design-craft | يطابق UI / Visual design: Try to break a piece of UI by feeding it worst-case data — long names, unbreakable emails, one-letter names, missing fields, huge counts |
| i18n-localization | ui-ux-design | يطابق i18n / RTL: Internationalization and localization patterns. Detecting hardcoded strings, managing translations, locale files, RTL support.. Use: When |

المهارات مثبتة في `.claude/skills` و `.agents/skills` وتُحمَّل عند الحاجة فقط؛ لا تُنسخ نصوصها هنا. قائمة ما حُقن وأسبابه في `skills.manifest.json`.
<!-- planning-studio:skills:end -->
