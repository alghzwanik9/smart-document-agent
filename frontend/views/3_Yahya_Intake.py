"""Yahya Intelligent Office System - Streamlit Governance & Intake View.
Taif University HR domain layer:
1. Intake & Prioritization evaluation (NO_MATCH, SIMILAR_FOUND, SAME_PERSON_NEW_TOPIC).
2. Hierarchy Search (PER -> CASE -> EV).
3. Append-only Sync & Audit Export (Markdown & JSON).
"""
from __future__ import annotations

from datetime import datetime, timezone
import streamlit as st

from utils import strings
from utils.api_client import ApiClient, ApiError, Unreachable, shared_client
from utils.rtl import inject_rtl

inject_rtl()


def render_yahya_view(client: ApiClient) -> None:
    st.title(strings.YAHYA_TITLE)
    st.caption(strings.YAHYA_CAPTION)

    tabs = st.tabs([strings.TAB_INTAKE, strings.TAB_SEARCH, strings.TAB_EXPORT])

    # ------------------------------------------------------------------ Tab 1: Intake & Evaluation
    with tabs[0]:
        st.subheader("تقييم وفرز المعاملات الواردة")
        st.caption("التحقق الآلي من السوابق، كشف الازدواجية، وتحديد أولوية المعاملة بناءً على المهل النظامية.")

        # Document selection helper
        doc_options = {}
        try:
            docs = client.list_documents(page=1, page_size=50).get("items", [])
            for d in docs:
                doc_options[d["id"]] = f"مستند #{d['id']}: {d['filename']} ({d['status']})"
        except Exception:
            pass

        selected_doc_id = None
        if doc_options:
            use_doc = st.checkbox("ربط المعاملة بمستند مرفوع مسبقاً", value=False)
            if use_doc:
                selected_doc_id = st.selectbox(
                    "اختر المستند",
                    options=list(doc_options.keys()),
                    format_func=lambda x: doc_options[x],
                )

        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("اسم الموظف / صاحب المعاملة *", key="intake_name")
            employee_number = st.text_input("الرقم الوظيفي (إن وجد)", key="intake_emp_no")
            national_id = st.text_input(
                "رقم الهوية الوطنية (للمطابقة المشفرة فقط)",
                key="intake_nid",
                help="يتم تشفيره فورياً ولا يظهر في رقم المعاملة أو الواجهة",
            )
            domain = st.selectbox(
                "نطاق المعاملة",
                options=["PAY", "LEG", "AUD", "COR"],
                format_func=lambda d: {
                    "PAY": "الرواتب والبدلات المالية (PAY)",
                    "LEG": "الشؤون القانونية والقضايا (LEG)",
                    "AUD": "المراجعة الداخلية والرقابة (AUD)",
                    "COR": "الاتصالات والمعاملات الإدارية (COR)",
                }.get(d, d),
                key="intake_domain",
            )

        with col2:
            subject = st.text_area("موضوع المعاملة / الدعوى *", key="intake_subj", height=105)
            reference_number = st.text_input("رقم المرجع / خطاب القيد / الدعوى", key="intake_ref")
            monetary_amount = st.number_input(
                "المبلغ المالي للمطالبة (ريال)",
                min_value=0.0,
                value=0.0,
                step=100.0,
                key="intake_amount",
            )
            deadline_date = st.date_input("الموعد النظامي النهائي (إن وجد)", value=None, key="intake_deadline")

        eval_button = st.button("تقييم المعاملة والتحقق من السوابق", type="primary")

        if eval_button:
            if not full_name.strip() or not subject.strip():
                st.error("يرجى إدخال اسم الموظف وموضوع المعاملة كحد أدنى.")
            else:
                deadline_iso = (
                    datetime.combine(deadline_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()
                    if deadline_date
                    else None
                )
                payload = {
                    "full_name": full_name.strip(),
                    "employee_number": employee_number.strip() if employee_number else None,
                    "national_id": national_id.strip() if national_id else None,
                    "subject": subject.strip(),
                    "reference_number": reference_number.strip() if reference_number else None,
                    "monetary_amount": float(monetary_amount) if monetary_amount > 0 else None,
                    "domain": domain,
                    "statutory_deadline": deadline_iso,
                    "document_id": selected_doc_id,
                }
                try:
                    res = client.evaluate_intake(payload)
                    st.session_state["last_eval_result"] = res
                    st.session_state["last_eval_payload"] = payload
                except (Unreachable, ApiError) as err:
                    st.error(f"تعذّر تقييم المعاملة: {err}")

        # Display Evaluation Results & Case Commitment
        if "last_eval_result" in st.session_state:
            res = st.session_state["last_eval_result"]
            payload = st.session_state["last_eval_payload"]

            st.divider()
            st.subheader("نتيجة التقييم الآلي وقرار التوجيه")

            decision = res.get("decision")
            prio = res.get("suggested_priority", "P2")
            days_rem = res.get("business_days_remaining")

            if decision == "NO_MATCH":
                st.success(f"القرار: {strings.DECISION_LABELS.get(decision, decision)}")
            elif decision == "SIMILAR_FOUND":
                st.warning(f"القرار: {strings.DECISION_LABELS.get(decision, decision)}")
            else:
                st.info(f"القرار: {strings.DECISION_LABELS.get(decision, decision)}")

            # Priority & Deadlines
            cols = st.columns(3)
            with cols[0]:
                st.metric("الأولوية المقترحة", strings.PRIORITY_LABELS.get(prio, prio))
            with cols[1]:
                st.metric(
                    "أيام العمل المتبقية نظاماً",
                    f"{days_rem} يوم" if days_rem is not None else "غير محدد",
                )
            with cols[2]:
                st.metric(
                    "ملف الموظف المسجل",
                    res["person"]["per_id"] if res.get("person") else "جديد (سيتم إنشاء ملف PER)",
                )

            st.write(f"**سبب التوجيه**: {res.get('reason', '')}")

            # Show Similar Cases if any
            sim_cases = res.get("similar_cases", [])
            if sim_cases:
                st.markdown("#### المعاملات السابقة المطابقة:")
                for sc in sim_cases:
                    with st.expander(f"معاملة #{sc['case_id']} — {sc['subject']}"):
                        st.write(f"- **ملف الموظف**: `{sc['per_id']}`")
                        st.write(f"- **الحالة الحالية**: `{strings.CASE_STATUS_LABELS.get(sc['status'], sc['status'])}`")
                        st.write(f"- **الحقول المتطابقة**: {', '.join(sc['matched_fields'])}")
                        st.write(f"- **الفروقات**: {', '.join(sc['differences'])}")
                        if sc.get("last_event"):
                            st.write(f"- **آخر إجراء مسجل**: {sc['last_event']}")

            st.divider()
            # Commit Case Section
            st.subheader("اعتماد وقيد المعاملة")
            st.caption("تسجيل المعاملة رسمياً في سجلات الجامعة وإنشاء حدث القيد الأولي (EV-001).")

            commit_cols = st.columns(2)
            with commit_cols[0]:
                final_prio = st.selectbox(
                    "الأولوية المعتمدة",
                    options=["P1", "P2", "P3"],
                    index=["P1", "P2", "P3"].index(prio) if prio in ["P1", "P2", "P3"] else 1,
                    key="commit_prio",
                )
            with commit_cols[1]:
                initial_notes = st.text_input(
                    "ملاحظة حدث القيد الأولي",
                    value="قيد المعاملة عبر نظام الاستقبال والفرز الآلي",
                    key="commit_notes",
                )

            if st.button("اعتماد وقيد المعاملة رسمياً (Commit Case)", type="primary"):
                create_body = {
                    "per_id": res["person"]["per_id"] if res.get("person") else None,
                    "employee_number": payload.get("employee_number"),
                    "full_name": payload.get("full_name"),
                    "national_id": payload.get("national_id"),
                    "subject": payload["subject"],
                    "domain": payload["domain"],
                    "priority": final_prio,
                    "statutory_deadline": payload.get("statutory_deadline"),
                    "reference_number": payload.get("reference_number"),
                    "monetary_amount": payload.get("monetary_amount"),
                    "document_id": payload.get("document_id"),
                    "initial_event_description": initial_notes.strip(),
                }
                try:
                    new_case = client.create_case(create_body)
                    st.success(
                        f"تم قيد المعاملة بنجاح برقم: {new_case['case_id']} تحت ملف الموظف: {new_case['per_id']}"
                    )
                    # Clear session state
                    del st.session_state["last_eval_result"]
                    del st.session_state["last_eval_payload"]
                except (Unreachable, ApiError) as err:
                    st.error(f"تعذّر اعتماد المعاملة: {err}")

    # ------------------------------------------------------------------ Tab 2: Hierarchy Search
    with tabs[1]:
        st.subheader("البحث الهرمي في ملفات الموظفين والمعاملات")
        st.caption("استعلام شامل عبر الاسم، الرقم الوظيفي، رقم المعاملة، أو رقم المرجع مع عرض التدرج الهرمي (PER ➔ CASE ➔ EV).")

        search_q = st.text_input("نص البحث", placeholder="أدخل اسم الموظف، الرقم الوظيفي، رقم المعاملة، أو رقم المرجع...")
        if search_q.strip():
            try:
                results = client.search_yahya(search_q.strip())
                if not results:
                    st.info("لم يتم العثور على أي نتائج مطابقة.")
                else:
                    st.write(f"تم العثور على {len(results)} ملف موظف مطابق:")
                    for p in results:
                        with st.container(border=True):
                            st.markdown(f"### ملف الموظف: {p['full_name']} (`{p['per_id']}`)")
                            col_p1, col_p2 = st.columns(2)
                            with col_p1:
                                st.write(f"**الرقم الوظيفي**: {p['employee_number'] or 'غير مسجل'}")
                            with col_p2:
                                st.write(f"**تاريخ القيد**: {p['created_at'][:10]}")

                            cases = p.get("cases", [])
                            st.markdown(f"**المعاملات المرتبطة ({len(cases)}):**")
                            for c in cases:
                                with st.expander(f"معاملة #{c['case_id']} — {c['subject']} [{strings.CASE_STATUS_LABELS.get(c['status'], c['status'])} | {c['priority']}]"):
                                    c_cols = st.columns(3)
                                    with c_cols[0]:
                                        st.write(f"- **النطاق**: {c['domain']}")
                                        st.write(f"- **الحالة**: {strings.CASE_STATUS_LABELS.get(c['status'], c['status'])}")
                                    with c_cols[1]:
                                        st.write(f"- **رقم المرجع**: {c.get('reference_number') or '-'}")
                                        st.write(f"- **الأولوية**: {c['priority']}")
                                    with c_cols[2]:
                                        amount_val = c.get('monetary_amount')
                                        st.write(f"- **المبلغ**: {amount_val:,.2f} ريال" if amount_val else "- **المبلغ**: -")
                                        st.write(f"- **الموعد**: {c['statutory_deadline'][:10] if c.get('statutory_deadline') else '-'}")

                                    # Events table
                                    events = c.get("events", [])
                                    if events:
                                        st.markdown("##### سجل الأحداث والتدقيق (Append-Only Events):")
                                        ev_data = [
                                            {
                                                "المعرف": e["ev_id"],
                                                "النوع": e["event_type"],
                                                "البيان": e["description"],
                                                "السابق": e.get("old_value") or "-",
                                                "الجديد": e.get("new_value") or "-",
                                                "السبب": e.get("reason") or "-",
                                                "التاريخ": e["created_at"][:16].replace("T", " "),
                                            }
                                            for e in events
                                        ]
                                        st.dataframe(ev_data, hide_index=True, width="stretch")
            except (Unreachable, ApiError) as err:
                st.error(f"خطأ أثناء البحث: {err}")

    # ------------------------------------------------------------------ Tab 3: Sync & Audit Export
    with tabs[2]:
        st.subheader("تصدير سجل المزامنة والتدقيق الشامل")
        st.caption("تصدير السجل الكامل غير القابل للتعديل بصيغة Markdown أو JSON لأغراض التدقيق الرقابي والمزامنة الخارجية.")

        export_cols = st.columns(2)
        with export_cols[0]:
            if st.button("تجهيز تصدير Markdown"):
                try:
                    resp = client.export_yahya_sync(format="markdown")
                    st.download_button(
                        label="تنزيل تقرير Markdown",
                        data=resp.text,
                        file_name=f"yahya_system_audit_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                        mime="text/markdown",
                    )
                    st.success("تم تجهيز التقرير بنجاح.")
                except (Unreachable, ApiError) as err:
                    st.error(f"تعذّر التصدير: {err}")

        with export_cols[1]:
            if st.button("تجهيز تصدير JSON"):
                try:
                    resp = client.export_yahya_sync(format="json")
                    st.download_button(
                        label="تنزيل بيانات JSON",
                        data=resp.text,
                        file_name=f"yahya_system_sync_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json",
                    )
                    st.success("تم تجهيز البيانات بنجاح.")
                except (Unreachable, ApiError) as err:
                    st.error(f"تعذّر التصدير: {err}")


render_yahya_view(shared_client())
