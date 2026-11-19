"""Builds sample_docs/onboarding-handbook.pdf (fictional, 3 pages) so page-number citations can be demonstrated."""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent.parent / "sample_docs" / "onboarding-handbook.pdf"

PAGES = [
    (
        "Brightpath Analytics — Employee Onboarding Handbook (fictional)",
        [
            "This is a fictional handbook created for demonstrating the AI Document Assistant.",
            "Welcome to Brightpath Analytics. Your first week is organised by your onboarding buddy, who is assigned before your start date and will meet you at reception at 9:30 on day one.",
            "On your first day you will receive your laptop, ID badge and access to email. Please bring a government photo ID and a cancelled cheque for payroll setup.",
        ],
    ),
    (
        "Leave and holidays",
        [
            "Full-time employees receive 24 days of paid annual leave per calendar year, accrued monthly at 2 days per month.",
            "Up to 10 unused leave days can be carried forward to the next year. Carried-forward days expire on 31 March.",
            "Sick leave is separate: employees receive 12 days of paid sick leave per year. A medical certificate is required for sick leave longer than 2 consecutive days.",
            "Leave requests are submitted in the PeopleHub portal and approved by your reporting manager.",
        ],
    ),
    (
        "Learning and development",
        [
            "Every employee has an annual learning budget of 40,000 rupees for courses, certifications and conference tickets.",
            "Certification exam fees are reimbursed after you pass the exam. Submit the certificate and receipt within 30 days.",
            "New engineers complete the internal Data Platform 101 course during their first month.",
        ],
    ),
]


def main() -> None:
    styles = getSampleStyleSheet()
    flow = []
    for i, (title, paras) in enumerate(PAGES):
        flow.append(Paragraph(title, styles["Heading1"]))
        for p in paras:
            flow += [Paragraph(p, styles["BodyText"]), Spacer(1, 8)]
        if i < len(PAGES) - 1:
            flow.append(PageBreak())
    SimpleDocTemplate(str(OUT), pagesize=A4, title="Onboarding Handbook (fictional)").build(flow)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
