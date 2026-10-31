import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

st.set_page_config(page_title="SL Express – Client Delivery Reporting Tool", layout="wide")

LOGO_URL = "https://i0.wp.com/slexpress.co.nz/wp-content/uploads/2023/05/Logo2.jpg?fit=1000%2C633&ssl=1"

st.sidebar.title("SL Express")
st.sidebar.image(LOGO_URL, use_container_width=True)
menu = st.sidebar.radio(
    "Menu",
    ["Generate Report", "Current Clients", "Lost Clients", "Create New Customer"]
)

# Default current clients
if "clients" not in st.session_state:
    st.session_state.clients = pd.DataFrame({
        "Client Name": [
            "Natasha Zhu / Evernine Grocery Store",
            "Storage King",
            "Plant and Pot / Martin"
        ],
        "Address": [
            "2/260 Oteha Valley Rd, Albany, Auckland 0632",
            "",
            ""
        ],
        "Email": [
            "everninegrocery@gmail.com",
            "",
            ""
        ],
        "Phone": [
            "0204451635",
            "",
            ""
        ],
        "Pricing Type": ["Tiered", "Flat", "Flat"],
        "0-15 km": [6.90, None, None],
        "15-25 km": [7.90, None, None],
        "25-35 km": [9.90, None, None],
        "35+ km": [13.90, None, None],
        "Flat Rate": [None, 5.90, 14.00]
    })

if "lost_clients" not in st.session_state:
    st.session_state.lost_clients = pd.DataFrame({"Client Name": [], "Notes": []})

def fuzzy_match(text, keywords):
    if pd.isna(text) or not keywords:
        return False
    t = str(text).lower()
    # Require at least one meaningful keyword match (length > 3 to avoid short words)
    meaningful = [k.lower() for k in keywords if len(str(k)) > 3]
    return any(k in t for k in meaningful)

# ---------- GENERATE REPORT ----------
if menu == "Generate Report":
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image(LOGO_URL, width=180)
    with col_title:
        st.title("SL Express – Client Delivery Reporting Tool")
        st.caption("Upload Shipday export → Select customers → Apply rates → Download or email report")

    DEFAULT_TIERS = {"0-15": 6.90, "15-25": 7.90, "25-35": 9.90, "35+": 13.90}

    def generate_detailed_pdf(df, client_name, total):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=6*mm, leftMargin=6*mm, topMargin=12*mm, bottomMargin=12*mm)
        styles = getSampleStyleSheet()
        elements = []
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=12, spaceAfter=3, alignment=TA_CENTER)
        elements.append(Paragraph("SL EXPRESS – Detailed Delivery Report", title_style))
        elements.append(Paragraph(f"<b>Client:</b> {client_name} &nbsp;&nbsp;&nbsp; <b>Period:</b> October 2026 &nbsp;&nbsp;&nbsp; <b>Total (incl GST):</b> ${total:,.2f}", styles['Normal']))
        elements.append(Spacer(1, 5*mm))

        col_map = {
            "Date": "Date", "Order No.": "Order No.", "Pick-up From": "Pick-up From",
            "Pick-up Address": "Pick-up Address", "Deliver To": "Deliver To",
            "Delivery Address": "Delivery Address", "Driver": "Driver",
            "Distance (km)": "Distance (km)", "Pricing Tier": "Tier",
            "Price (incl GST)": "Price", "Status": "Status", "Proof of Delivery": "Proof"
        }
        display_df = df.copy()
        if "Distance    (km)" in display_df.columns and "Distance (km)" not in display_df.columns:
            display_df = display_df.rename(columns={"Distance    (km)": "Distance (km)"})

        available_keys = [k for k in col_map.keys() if k in display_df.columns]
        headers = [col_map[k] for k in available_keys]
        wrap_style = ParagraphStyle('WrapStyle', parent=styles['Normal'], fontSize=6, leading=7.5, alignment=TA_LEFT)
        link_style = ParagraphStyle('LinkStyle', parent=styles['Normal'], fontSize=6.5, textColor=colors.HexColor("#1a56db"), alignment=TA_CENTER)

        table_data = [headers]
        for _, row in display_df.iterrows():
            row_data = []
            for key in available_keys:
                val = row.get(key, "")
                if pd.isna(val): val = ""
                val = str(val).strip()
                if key == "Price (incl GST)":
                    try: val = f"${float(val):.2f}"
                    except: pass
                if key == "Proof of Delivery" and val.startswith("http"):
                    row_data.append(Paragraph(f'<link href="{val}" color="blue"><u>View</u></link>', link_style))
                elif len(val) > 22:
                    row_data.append(Paragraph(val[:70], wrap_style))
                else:
                    row_data.append(val)
            table_data.append(row_data)

        widths = {"Date": 20*mm, "Order No.": 30*mm, "Pick-up From": 32*mm, "Pick-up Address": 36*mm,
                  "Deliver To": 26*mm, "Delivery Address": 40*mm, "Driver": 18*mm, "Distance (km)": 16*mm,
                  "Pricing Tier": 28*mm, "Price (incl GST)": 16*mm, "Status": 18*mm, "Proof of Delivery": 16*mm}
        col_widths = [widths.get(k, 22*mm) for k in available_keys]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1a365d")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 6.5),
            ('FONTSIZE', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 6*mm))
        elements.append(Paragraph(f"<i>Total deliveries: {len(df)} | Total amount: ${total:,.2f} (GST inclusive). Click View to open proof.</i>", styles['Normal']))
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    uploaded = st.file_uploader("Upload Shipday order report (Excel or CSV)", type=["xlsx", "xls", "csv"])

    # Extract month and year from filename
    period_text = "October 2026"  # fallback
    if uploaded:
        fname = uploaded.name.lower()
        months = ["january","february","march","april","may","june","july","august","september","october","november","december"]
        found_month = None
        found_year = None
        for m in months:
            if m in fname:
                found_month = m.capitalize()
                break
        import re
        year_match = re.search(r"20\d{2}", fname)
        if year_match:
            found_year = year_match.group()
        if found_month and found_year:
            period_text = f"{found_month} {found_year}"
        elif found_month:
            period_text = found_month
        st.caption(f"Detected period from filename: **{period_text}**")

    if uploaded:
        try:
            if uploaded.name.endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                df = pd.read_excel(uploaded, header=1)
            df.columns = [str(c).replace("\xa0", " ").strip() for c in df.columns]
            dist_col = next((c for c in df.columns if "Distance" in c), None)
            if not dist_col:
                st.error("Distance column not found.")
                st.stop()
            df[dist_col] = pd.to_numeric(df[dist_col], errors="coerce")

            # Build keyword list from current clients
            client_keywords = []
            for name in st.session_state.clients["Client Name"].dropna():
                for part in str(name).replace("/", " ").split():
                    if len(part) > 2:
                        client_keywords.append(part)

            # Auto-select matching rows
            pickup_match = df["Pick-up From"].apply(lambda x: fuzzy_match(x, client_keywords)) if "Pick-up From" in df.columns else False
            deliver_match = df["Deliver To"].apply(lambda x: fuzzy_match(x, client_keywords)) if "Deliver To" in df.columns else False
            auto_mask = pickup_match | deliver_match

            st.write(f"**Auto-matched {auto_mask.sum()} deliveries** based on current client names (checked both Pick-up From and Deliver To).")

            selected_clients = st.multiselect(
                "Confirm or adjust client selection (matches current clients)",
                options=st.session_state.clients["Client Name"].tolist(),
                default=st.session_state.clients["Client Name"].tolist()[:3]
            )

            if selected_clients:
                # Build final mask from selected client keywords
                sel_keywords = []
                for name in selected_clients:
                    # Keep longer, more specific parts only
                    for part in str(name).replace("/", " ").replace("-", " ").split():
                        clean = part.strip()
                        if len(clean) > 3 and clean.lower() not in ["and", "the", "for", "with"]:
                            sel_keywords.append(clean)
                final_mask = df["Pick-up From"].apply(lambda x: fuzzy_match(x, sel_keywords)) | df["Deliver To"].apply(lambda x: fuzzy_match(x, sel_keywords))
                client_df = df[final_mask].copy()
                st.write(f"**{len(client_df)} deliveries** selected for report.")

                invoice_client_name = st.text_input("Client name on invoice", value=selected_clients[0] if selected_clients else "")

                special_day = st.checkbox("Apply special $5 rate for 0–15 km on 31 October 2026 (Evernine only)", value=True)

                def get_price(row):
                    status = str(row.get("Status", ""))
                    if "Failed" in status and "Waive" in status:
                        return 0.0
                    pickup = str(row.get("Pick-up From", "")).lower()
                    deliver = str(row.get("Deliver To", "")).lower()
                    text = pickup + " " + deliver
                    km = row[dist_col]
                    if pd.isna(km):
                        return 0.0
                    if "storage king" in text:
                        return 5.90
                    if ("plant" in text and "pot" in text) or "martin" in text:
                        return 14.00
                    date_str = str(row.get("Date", ""))
                    if special_day and any(x in date_str for x in ["Oct 31", "31 Oct", "October 31"]) and km <= 15:
                        return 5.00
                    if km <= 15: return DEFAULT_TIERS["0-15"]
                    elif km <= 25: return DEFAULT_TIERS["15-25"]
                    elif km <= 35: return DEFAULT_TIERS["25-35"]
                    else: return DEFAULT_TIERS["35+"]

                client_df["Price (incl GST)"] = client_df.apply(get_price, axis=1)

                def get_tier(row):
                    status = str(row.get("Status", ""))
                    if "Failed" in status and "Waive" in status:
                        return "Waived"
                    pickup = str(row.get("Pick-up From", "")).lower()
                    deliver = str(row.get("Deliver To", "")).lower()
                    text = pickup + " " + deliver
                    km = row[dist_col]
                    if "storage king" in text: return "Flat $5.90"
                    if ("plant" in text and "pot" in text) or "martin" in text: return "Flat $14.00"
                    date_str = str(row.get("Date", ""))
                    if special_day and any(x in date_str for x in ["Oct 31", "31 Oct", "October 31"]) and km <= 15:
                        return "0-15 km (31 Oct special $5)"
                    if km <= 15: return "0-15 km"
                    elif km <= 25: return "15-25 km"
                    elif km <= 35: return "25-35 km"
                    else: return "35+ km"

                client_df["Pricing Tier"] = client_df.apply(get_tier, axis=1)
                total = client_df["Price (incl GST)"].sum()
                st.metric("Total Invoice Amount (incl GST)", f"${total:,.2f}")

                display_cols = ["Date", "Order No.", "Pick-up From", "Deliver To", "Pick-up Address", "Delivery Address", "Driver", dist_col, "Pricing Tier", "Price (incl GST)", "Status", "Proof of Delivery"]
                display_cols = [c for c in display_cols if c in client_df.columns]
                st.dataframe(client_df[display_cols].sort_values("Date"), use_container_width=True)

                # Downloads
                col1, col2, col3 = st.columns(3)
                with col1:
                    excel_buf = BytesIO()
                    client_df.to_excel(excel_buf, index=False)
                    st.download_button("Download Detailed Excel", excel_buf.getvalue(), f"detailed_report_{period_text.replace(' ', '_')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                with col2:
                    pdf_detailed = generate_detailed_pdf(client_df, invoice_client_name, total)
                    st.download_button("Download Detailed PDF (Landscape)", pdf_detailed, f"Detailed_Report_{period_text.replace(' ', '_')}.pdf", "application/pdf")
                with col3:
                    # Professional invoice matching sample format
                    from datetime import datetime, timedelta
                    invoice_date = datetime.now()
                    due_date = invoice_date + timedelta(days=7)
                    # Auto invoice number from initials
                    initials = "".join([w[0].upper() for w in invoice_client_name.split() if w])[:3]
                    inv_num = f"{initials}-{invoice_date.strftime('%y%m%d')}"

                    # Get exact address from Current Clients
                    bill_address = ""
                    for _, crow in st.session_state.clients.iterrows():
                        client_name_saved = str(crow["Client Name"]).lower()
                        if invoice_client_name.lower() in client_name_saved or any(part.lower() in client_name_saved for part in invoice_client_name.split() if len(part) > 2):
                            bill_address = str(crow.get("Address", "")).strip()
                            if bill_address and bill_address.lower() != "nan":
                                break
                    if not bill_address:
                        bill_address = "(Address not set in Current Clients)"

                    pdf_buf = BytesIO()
                    c = canvas.Canvas(pdf_buf, pagesize=A4)
                    w, h = A4

                    # Header
                    c.setFont("Helvetica-Bold", 14)
                    c.drawString(20*mm, h-18*mm, "Sable Logistics Ltd")
                    c.setFont("Helvetica", 9)
                    c.drawString(20*mm, h-24*mm, "2/15 Starforth Place, Henderson, Auckland 0612")
                    c.drawString(20*mm, h-29*mm, "GST No: 136-663-313")

                    c.setFont("Helvetica-Bold", 16)
                    c.drawRightString(w-20*mm, h-18*mm, "TAX INVOICE")

                    # Logo under TAX INVOICE
                    try:
                        import urllib.request
                        from reportlab.lib.utils import ImageReader
                        logo_data = urllib.request.urlopen(LOGO_URL).read()
                        logo_img = ImageReader(BytesIO(logo_data))
                        c.drawImage(logo_img, w-55*mm, h-42*mm, width=35*mm, height=22*mm, preserveAspectRatio=True, mask='auto')
                    except Exception:
                        pass  # continue without logo if download fails

                    # Bill To
                    c.setFont("Helvetica-Bold", 10)
                    c.drawString(20*mm, h-45*mm, "Bill To")
                    c.setFont("Helvetica", 9)
                    c.drawString(20*mm, h-51*mm, invoice_client_name)
                    y = h-56*mm
                    for line in bill_address.split(","):
                        c.drawString(20*mm, y, line.strip())
                        y -= 5*mm

                    # Invoice details
                    c.setFont("Helvetica-Bold", 9)
                    c.drawRightString(w-20*mm, h-45*mm, f"Invoice #  {inv_num}")
                    c.setFont("Helvetica", 9)
                    c.drawRightString(w-20*mm, h-51*mm, f"Invoice Date  {invoice_date.strftime('%d/%m/%Y')}")

                    # Table
                    data = [
                        ["QTY", "DESCRIPTION", "UNIT PRICE", "AMOUNT"],
                        [str(len(client_df)), f"{len(client_df)} Total deliveries in October 2026\n(Total price is inclusive of GST)", f"{total/len(client_df):.2f}" if len(client_df) else "0.00", f"{total:.2f}"],
                        ["", "", "TOTAL", f"$ {total:.2f}"]
                    ]
                    table = Table(data, colWidths=[20*mm, 90*mm, 35*mm, 35*mm])
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f0f0f0")),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,-1), 8),
                        ('ALIGN', (2,1), (-1,-1), 'RIGHT'),
                        ('GRID', (0,0), (-1,-2), 0.5, colors.grey),
                        ('BACKGROUND', (2,-1), (-1,-1), colors.HexColor("#f7f7f7")),
                        ('FONTNAME', (2,-1), (-1,-1), 'Helvetica-Bold'),
                        ('SPAN', (0,-1), (1,-1)),
                    ]))
                    table.wrapOn(c, w, h)
                    table.drawOn(c, 20*mm, h-100*mm)

                    # Payment terms
                    c.setFont("Helvetica-Bold", 9)
                    c.drawString(20*mm, 55*mm, f"Payment due 7 days from invoice date ({due_date.strftime('%d/%m/%Y')})")
                    c.setFont("Helvetica", 8)
                    c.drawString(20*mm, 48*mm, "EFT Details:")
                    c.drawString(20*mm, 43*mm, "Bank: ASB")
                    c.drawString(20*mm, 38*mm, "Bank Account Name: Sable Logistics Ltd")
                    c.drawString(20*mm, 33*mm, "Account Number: 12-3449-0228471-00")
                    c.drawString(20*mm, 28*mm, "Please use Invoice Number as reference.")

                    c.save()
                    invoice_pdf = pdf_buf.getvalue()
                    st.download_button("Download Summary Invoice PDF", invoice_pdf, f"Invoice_{inv_num}_{period_text.replace(' ', '_')}.pdf", "application/pdf")

                st.subheader("Tier Summary")
                summary = client_df.groupby("Pricing Tier")["Price (incl GST)"].agg(["count", "sum"]).reset_index()
                summary.columns = ["Tier", "Deliveries", "Amount"]
                st.table(summary)

                # Email section (Crazy Domains)
                st.subheader("Email Invoice & Report")
                customer_email = ""
                for _, crow in st.session_state.clients.iterrows():
                    if any(part.lower() in str(crow["Client Name"]).lower() for part in invoice_client_name.split()):
                        customer_email = crow.get("Email", "")
                        break
                to_email = st.text_input("Send to email", value=customer_email)
                
                default_subject = f"SL Express Invoice – {invoice_client_name} – {period_text}"
                email_subject = st.text_input("Email subject (editable)", value=default_subject)

                default_body = f"""Dear {invoice_client_name},

Please find attached your {period_text} delivery invoice and detailed report.

Total due: ${total:,.2f} (GST inclusive)

Payment is due within 7 days.

Thank you for your business.

Kind regards,
SL Express
customercare@slexpress.co.nz
www.slexpress.co.nz"""

                email_body = st.text_area("Email body (you can edit this before sending)", value=default_body, height=180)
                
                smtp_server = st.text_input("SMTP Server", value="mail.slexpress.co.nz")
                smtp_port = st.number_input("SMTP Port", value=587, step=1)
                smtp_password = st.text_input("Password for customercare@slexpress.co.nz (not saved)", type="password")

                if st.button("Send Email") and to_email and smtp_password:
                    try:
                        msg = MIMEMultipart()
                        msg["From"] = "customercare@slexpress.co.nz"
                        msg["To"] = to_email
                        msg["Subject"] = email_subject
                        msg.attach(MIMEText(email_body, "plain"))
                        msg.attach(MIMEApplication(invoice_pdf, Name="Invoice.pdf"))
                        msg.attach(MIMEApplication(pdf_detailed, Name=f"Detailed_Report_{period_text.replace(' ', '_')}.pdf"))

                        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
                            server.starttls()
                            server.login("customercare@slexpress.co.nz", smtp_password)
                            server.send_message(msg)
                        st.success(f"Email sent to {to_email}")
                    except Exception as e:
                        st.error(f"Email failed: {e}. Try smtp server 'mail.slexpress.co.nz' or check password.")

        except Exception as e:
            st.error(f"Error: {e}")
    else:
        st.info("Please upload a Shipday order report to begin.")

# ---------- CURRENT CLIENTS ----------
elif menu == "Current Clients":
    st.image(LOGO_URL, width=150)
    st.title("Current Clients")
    st.write("Edit rates, emails, or add rows. Staff can update this anytime.")
    edited = st.data_editor(st.session_state.clients, num_rows="dynamic", use_container_width=True, key="clients_editor")
    st.session_state.clients = edited
    if st.button("Save Changes"):
        st.success("Current clients updated.")

# ---------- LOST CLIENTS ----------
elif menu == "Lost Clients":
    st.image(LOGO_URL, width=150)
    st.title("Lost Clients")
    if st.session_state.lost_clients.empty:
        st.info("No lost clients yet.")
    else:
        st.dataframe(st.session_state.lost_clients, use_container_width=True)
    with st.form("add_lost"):
        name = st.text_input("Client name to mark as lost")
        notes = st.text_area("Notes")
        if st.form_submit_button("Add to Lost Clients") and name:
            new_row = pd.DataFrame({"Client Name": [name], "Notes": [notes]})
            st.session_state.lost_clients = pd.concat([st.session_state.lost_clients, new_row], ignore_index=True)
            st.success(f"{name} added.")
            st.rerun()

# ---------- CREATE NEW CUSTOMER ----------
elif menu == "Create New Customer":
    st.image(LOGO_URL, width=150)
    st.title("Create New Customer")
    with st.form("new_customer"):
        name = st.text_input("Customer Name *")
        address = st.text_area("Address")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        pricing_type = st.radio("Pricing Type", ["Tiered (distance brackets)", "Flat Rate (same price for all distances)"], horizontal=True)
        flat_rate = None
        if pricing_type.startswith("Flat"):
            flat_rate = st.number_input("Flat Rate (incl GST)", min_value=0.0, value=5.90, step=0.10, format="%.2f")
        else:
            st.write("Edit the distance brackets:")
            pricing_df = st.data_editor(
                pd.DataFrame({"Distance From (km)": [0, 15, 25, 35], "Distance To (km)": [15, 25, 35, 999], "Rate (incl GST)": [6.90, 7.90, 9.90, 13.90]}),
                num_rows="dynamic", use_container_width=True, key="new_pricing"
            )
        if st.form_submit_button("Create Customer") and name:
            if pricing_type.startswith("Flat"):
                new_client = pd.DataFrame({
                    "Client Name": [name], "Address": [address], "Email": [email], "Phone": [phone],
                    "Pricing Type": ["Flat"], "0-15 km": [None], "15-25 km": [None], "25-35 km": [None], "35+ km": [None], "Flat Rate": [flat_rate]
                })
            else:
                first = pricing_df["Rate (incl GST)"].iloc[0] if len(pricing_df) else None
                new_client = pd.DataFrame({
                    "Client Name": [name], "Address": [address], "Email": [email], "Phone": [phone],
                    "Pricing Type": ["Tiered"], "0-15 km": [first], "15-25 km": [None], "25-35 km": [None], "35+ km": [None], "Flat Rate": [None]
                })
            st.session_state.clients = pd.concat([st.session_state.clients, new_client], ignore_index=True)
            st.success(f"Customer '{name}' created.")
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("SL Express Reporting Tool – for staff use")
