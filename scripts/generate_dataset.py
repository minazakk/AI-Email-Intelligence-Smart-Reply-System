"""Reproducible synthetic dataset generator.

Creates 90 synthetic emails (10 per group, 9 groups) with expected labels,
expected extractions and expected deadlines. All identities, companies,
order ids and contact details are fake.

Usage:
    python scripts/generate_dataset.py [--out tests/fixtures/sample_emails.json]
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta

GROUPS = (
    "customer_complaint",
    "sales_inquiry",
    "support_request",
    "meeting_request",
    "invoice_payment",
    "job_application",
    "general_information",
    "urgent",
    "spam",
)

PERSONAS = [
    {
        "name": "Anna Reyes",
        "first": "Anna",
        "company": "Blue Harbor Logistics",
        "domain": "blueharbor-logistics.example",
    },
    {
        "name": "Daniel Okafor",
        "first": "Daniel",
        "company": "Northwind Retail Group",
        "domain": "northwind-retail.example",
    },
    {"name": "Priya Raman", "first": "Priya", "company": "Cedar Analytics Ltd", "domain": "cedaranalytics.example"},
    {"name": "Marcus Feld", "first": "Marcus", "company": "Helio Manufacturing", "domain": "helio-mfg.example"},
    {
        "name": "Sofia Marchetti",
        "first": "Sofia",
        "company": "Verde Hospitality",
        "domain": "verde-hospitality.example",
    },
    {"name": "Tomas Novak", "first": "Tomas", "company": "Arcline Studios", "domain": "arcline-studios.example"},
    {
        "name": "Grace Whitfield",
        "first": "Grace",
        "company": "Meridian Health Partners",
        "domain": "meridian-health.example",
    },
    {"name": "Kenji Watanabe", "first": "Kenji", "company": "Sakura Components", "domain": "sakura-components.example"},
    {"name": "Leyla Demir", "first": "Leyla", "company": "Anatolia Textiles", "domain": "anatolia-textiles.example"},
    {"name": "Owen Gallagher", "first": "Owen", "company": "Fitzgerald & Sons", "domain": "fitzgerald-sons.example"},
]

STAFF = "Alex Morgan <alex.morgan@ourcorp.example>"


# Reference window: September 2025 (deterministic timestamps).
def _received_at(index: int) -> datetime:
    day = 1 + (index * 3) % 20
    hour = 8 + (index * 5) % 9
    minute = (index * 7) % 60
    return datetime(2025, 9, day, hour, minute, tzinfo=UTC)


def _next_weekday(ref: date, weekday: int) -> date:
    delta = (weekday - ref.weekday()) % 7
    return ref + timedelta(days=delta)


def _deadline_due(phrase: str, ref: datetime) -> date | None:
    """Independent expected-date calculation (does not use the module)."""
    today = ref.date()
    lowered = phrase.lower()
    if "tomorrow" in lowered:
        return today + timedelta(days=1)
    if "today" in lowered:
        return today
    if "within 3 days" in lowered:
        return today + timedelta(days=3)
    if "within 24 hours" in lowered:
        return None
    if "friday" in lowered:
        return _next_weekday(today, 4)
    if "monday" in lowered:
        return _next_weekday(today, 0)
    if "end of this month" in lowered:
        if today.month == 12:
            return date(today.year, 12, 31)
        return date(today.year, today.month + 1, 1) - timedelta(days=1)
    if "25 september 2025" in lowered:
        return date(2025, 9, 25)
    if "2025-10-03" in lowered:
        return date(2025, 10, 3)
    return None


# Each entry: (subject, body, expected dict)
def _entries() -> dict[str, list[tuple[str, str, dict]]]:
    return {
        "customer_complaint": [
            (
                "Refund request - item arrived damaged",
                "Hi, my order {order} arrived damaged and the packaging was crushed. "
                "This is unacceptable and I want a refund of {amount} {currency}. "
                "Please confirm the refund within 3 days. {name}",
                {
                    "priority": "medium",
                    "sentiment": "angry",
                    "order_number": "{order}",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": "within 3 days",
                },
            ),
            (
                "Terrible service at your Leeds branch",
                "I am writing a formal complaint about the rude treatment I received at your Leeds branch. "
                "Your staff ignored my complaint for twenty minutes and this is unacceptable.",
                {"priority": "medium", "sentiment": "angry", "deadline": None},
            ),
            (
                "Wrong item delivered again",
                "Hello, you sent the wrong item with order {order}. I am disappointed because this is the second time. "
                "Please send the correct product and arrange a collection.",
                {"priority": "medium", "sentiment": "negative", "order_number": "{order}", "deadline": None},
            ),
            (
                "Charged twice for my subscription",
                "Hi team, my card was charged twice for the annual subscription of {amount} {currency}. "
                "I am dissatisfied and consider this a formal complaint. Please reverse the duplicate payment and confirm by Friday.",
                {
                    "priority": "medium",
                    "sentiment": "negative",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": "by Friday",
                },
            ),
            (
                "Order arrived broken - third time",
                "Hi, my order {order} arrived broken again. Three deliveries in a row arrived broken. "
                "I am unhappy and expect a replacement immediately.",
                {"priority": "critical", "sentiment": "negative", "order_number": "{order}", "deadline": None},
            ),
            (
                "Still waiting for my refund",
                "I submitted my refund request two weeks ago and I am still waiting for a reply. "
                "Nobody answers my calls and this poor service must be escalated.",
                {"priority": "high", "sentiment": "negative", "deadline": None},
            ),
            (
                "Formal complaint about repeated delays",
                "Dear team, this is a formal complaint about the repeated delays with order {order}. "
                "I remain dissatisfied with the outcome so far and expect a written explanation.",
                {"priority": "medium", "sentiment": "negative", "order_number": "{order}", "deadline": None},
            ),
            (
                "Rude behaviour from your representative",
                "Yesterday your representative was rude and dismissive on the phone. "
                "I am angry about the way my request was handled and I want a manager to call me back.",
                {"priority": "medium", "sentiment": "angry", "deadline": None},
            ),
            (
                "Quality of the delivered goods is unacceptable",
                "The batch we received under order {order} has poor stitching and two pieces were damaged. "
                "The quality is below the standard for our retail shelves.",
                {"priority": "medium", "sentiment": "angry", "order_number": "{order}", "deadline": None},
            ),
            (
                "Unhappy with the renewal price increase",
                "Hi, I am unhappy about the surprise renewal price and I consider this a formal complaint. "
                "The new price of {amount} {currency} was never confirmed with me and I want the previous price restored.",
                {
                    "priority": "medium",
                    "sentiment": "negative",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": None,
                },
            ),
        ],
        "sales_inquiry": [
            (
                "Request for quotation - 50 units",
                "Hello, we would like a quotation for 50 units of the standard model. "
                "Please share the price list and lead time. My name is {name} from {company}.",
                {"priority": "medium", "sentiment": "neutral", "customer_name": "{name}", "deadline": None},
            ),
            (
                "Pricing for the enterprise plan",
                "Hi, could you send pricing for the enterprise plan? We expect around 200 seats "
                "and would like to compare tiers before our budget review.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Interested in a bulk purchase",
                "Good morning, I am interested in a bulk purchase of your cleaning supplies. "
                "How much does a pallet of 200 boxes cost?",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Question about the product catalogue",
                "Hello, the catalogue lists two variants of the pump. Could you clarify which one suits salt water? "
                "We are ready to buy once we confirm the specification.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Partnership proposal for the northern region",
                "Dear sales team, {company} would like to propose a distribution partnership for the northern region. "
                "Please share your proposal template and partner pricing.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Discount for an annual subscription",
                "Hi, we plan to renew for a full year. Is a discount available if we commit annually? "
                "A quick confirmation would help us finalise the budget.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "How much does the premium tier cost?",
                "Could you tell me how much the premium tier costs per month, and whether setup is included? "
                "Thank you for your help.",
                {"priority": "medium", "sentiment": "positive", "deadline": None},
            ),
            (
                "Vendor enquiry for office supplies",
                "Hello, we are comparing vendors for office supplies and would like your catalogue and pricing. "
                "Please send a formal quotation for the items below.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Price list for the new range",
                "Hi there, please share the price list for the new range. We plan to purchase before the quarter closes. "
                "Much appreciated.",
                {"priority": "medium", "sentiment": "positive", "deadline": None},
            ),
            (
                "Quote needed for a trade show booth",
                "We need a quote for a modular trade show booth. Kindly include setup and teardown in the price.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
        ],
        "support_request": [
            (
                "Unable to log in to my account",
                "Hi support, I cannot log in to my account after the password reset. "
                "I need access by end of day today to finish a report. My email is {email}.",
                {
                    "priority": "critical",
                    "sentiment": "urgent",
                    "email_address": "{email}",
                    "deadline": "by end of day today",
                },
            ),
            (
                "Bug in the CSV export feature",
                "Hello, the CSV export button produces an empty file for large date ranges. "
                "This bug blocks our monthly reporting and we are disappointed by the regression.",
                {"priority": "medium", "sentiment": "negative", "deadline": None},
            ),
            (
                "API returns 500 error on upload",
                "Our integration now returns a 500 error on every upload request. "
                "Could you check the API status and advise?",
                {"priority": "medium", "sentiment": "negative", "deadline": None},
            ),
            (
                "Dashboard keeps crashing",
                "Hi, the dashboard keeps crashing when I open the analytics tab. "
                "I already cleared the cache but the crash still happens and I am unhappy about it.",
                {"priority": "medium", "sentiment": "negative", "deadline": None},
            ),
            (
                "Password reset link is not working",
                "The password reset link is not working; it says the token has expired. "
                "Please send a fresh link so I can get back in.",
                {"priority": "medium", "sentiment": "negative", "deadline": None},
            ),
            (
                "How do I add a new user?",
                "Hello, how do I add a new user to our workspace? "
                "I found the settings page but cannot see the invite option.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Timeout when uploading attachments",
                "Uploading attachments over 20 MB always times out for our team, so our uploads are lost. "
                "Is there a larger limit available on the business plan?",
                {"priority": "medium", "sentiment": "negative", "deadline": None},
            ),
            (
                "Broken link in the monthly report",
                "Hi, the link to last month's report in your newsletter returns a 404 error. "
                "Could you republish the document? Thank you.",
                {"priority": "medium", "sentiment": "negative", "deadline": None},
            ),
            (
                "Data sync fails between our systems",
                "Since Tuesday the data sync fails with a timeout message every hour and our synced records are lost. "
                "Please have engineering look into it urgently.",
                {"priority": "high", "sentiment": "negative", "deadline": None},
            ),
            (
                "Troubleshooting steps for the printer",
                "Could you share troubleshooting steps for the label printer? "
                "It prints blank labels after the last firmware update.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
        ],
        "meeting_request": [
            (
                "Schedule a call this week",
                "Hi, could we schedule a call this week to review the rollout plan? "
                "My availability is Tuesday to Thursday in the afternoon.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Meeting request - quarterly review",
                "Hello, I would like to arrange the quarterly review meeting. "
                "Please propose two slots that work for your team.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Availability for a product demo",
                "Hi, are you available for a product demo? Please confirm a time by 25 September 2025.",
                {
                    "priority": "medium",
                    "sentiment": "neutral",
                    "meeting_date": "25 September 2025",
                    "deadline": "25 September 2025",
                },
            ),
            (
                "Can we sync up on Tuesday?",
                "Would Tuesday work for a quick sync up about the migration? Thirty minutes should be enough.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Invite to the project kickoff meeting",
                "Hello, I invite you to the project kickoff meeting next week. Please reply with your preferred day.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Reschedule our appointment",
                "I need to reschedule our appointment because of a conflict. Could we meet the following week instead?",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Video call to discuss the contract",
                "Let's set up a video call to discuss the contract terms. I can join any afternoon this week.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Calendar invite for the workshop",
                "Please send a calendar invite for the workshop by 2025-10-03. Four people from our team will attend.",
                {"priority": "medium", "sentiment": "neutral", "meeting_date": "2025-10-03", "deadline": "2025-10-03"},
            ),
            (
                "Please find a slot for the monthly check-in",
                "Hi, please find a slot for our monthly check-in. We would like to keep it to forty-five minutes.",
                {"priority": "medium", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Brief call to introduce the new team",
                "Could we schedule a call to introduce the new team? Thanks for your time.",
                {"priority": "medium", "sentiment": "positive", "deadline": None},
            ),
        ],
        "invoice_payment": [
            (
                "Invoice INV-4471 is overdue",
                "Dear customer, invoice INV-4471 for {amount} {currency} is overdue. "
                "Please arrange payment within 3 days to avoid service interruption.",
                {
                    "priority": "high",
                    "sentiment": "neutral",
                    "invoice_number": "INV-4471",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": "within 3 days",
                },
            ),
            (
                "Payment received - receipt requested",
                "Hello, we sent the payment of {amount} {currency} on 10 September 2025. "
                "Could you please send the official receipt for our records? Thank you.",
                {
                    "priority": "medium",
                    "sentiment": "positive",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": None,
                },
            ),
            (
                "Reminder: outstanding balance on account 88213",
                "This is a friendly reminder that the outstanding balance of {amount} {currency} remains unpaid. "
                "Kindly settle it by Friday.",
                {
                    "priority": "medium",
                    "sentiment": "neutral",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": "by Friday",
                },
            ),
            (
                "Bank transfer details for the July invoice",
                "Hello, attached are the bank transfer details for invoice INV-3390. "
                "Please confirm once the payment reaches your account.",
                {"priority": "medium", "sentiment": "neutral", "invoice_number": "INV-3390", "deadline": None},
            ),
            (
                "Purchase order for billing - PO-5521",
                "Our purchase order PO-5521 is approved. Please raise the invoice for {amount} {currency} "
                "so our accounts team can process it.",
                {
                    "priority": "medium",
                    "sentiment": "neutral",
                    "order_number": "PO-5521",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": None,
                },
            ),
            (
                "Please confirm the payment due date",
                "Could you confirm the payment due date for order {order}? "
                "Our finance team needs the exact date before releasing the transfer.",
                {"priority": "medium", "sentiment": "neutral", "order_number": "{order}", "deadline": None},
            ),
            (
                "Final notice: payment overdue on INV-4402",
                "Final notice: payment for invoice INV-4402 is overdue by ten days. "
                "Please settle the amount of {amount} {currency} today.",
                {
                    "priority": "high",
                    "sentiment": "neutral",
                    "invoice_number": "INV-4402",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": None,
                },
            ),
            (
                "Request a copy of my receipt",
                "Hello, could you send a copy of the receipt for order {order}? "
                "The original email never arrived. Thank you.",
                {"priority": "medium", "sentiment": "positive", "order_number": "{order}", "deadline": None},
            ),
            (
                "Remittance advice for September invoices",
                "Please find the remittance advice covering invoices INV-4410 and INV-4411. "
                "Both payments were released by our bank today.",
                {"priority": "medium", "sentiment": "neutral", "invoice_number": "INV-4410", "deadline": None},
            ),
            (
                "Billing query about the annual subscription",
                "Hi, our annual subscription was invoiced at {amount} {currency} instead of the quoted rate. "
                "Please review the billing and advise.",
                {
                    "priority": "medium",
                    "sentiment": "neutral",
                    "amount": "{amount}",
                    "currency": "{currency}",
                    "deadline": None,
                },
            ),
        ],
        "job_application": [
            (
                "Application for the Marketing Manager role",
                "Dear hiring team, I am applying for the Marketing Manager position. "
                "My resume and cover letter are attached for your review.",
                {"priority": "low", "sentiment": "neutral", "deadline": None},
            ),
            (
                "My resume for the developer role",
                "Hello, please find my resume attached for the developer role. "
                "I have six years of experience with Python services.",
                {"priority": "low", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Cover letter for the design position",
                "Hi, I have attached my cover letter for the design position. "
                "I would be glad to walk through my portfolio on a call.",
                {"priority": "low", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Following up on my interview",
                "Thank you for the interview on Monday. I enjoyed the conversation "
                "and I am happy to provide any further information.",
                {"priority": "low", "sentiment": "positive", "deadline": None},
            ),
            (
                "Candidate for the sales position",
                "Dear recruiter, I am a candidate for the sales position and submitted my application last week. "
                "Please confirm that it was received.",
                {"priority": "low", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Applying for the internship programme",
                "Hello, I am applying for the internship programme starting in January. "
                "My CV is attached along with two reference contacts.",
                {"priority": "low", "sentiment": "neutral", "deadline": None},
            ),
            (
                "CV for your review - analyst role",
                "Please review my CV for the analyst role. I can start at two weeks' notice if selected.",
                {"priority": "low", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Job opening enquiry - support engineer",
                "Hi, I saw the job opening for a support engineer on your careers page. "
                "Is the vacancy still open for applications?",
                {"priority": "low", "sentiment": "neutral", "deadline": None},
            ),
            (
                "Interview availability next week",
                "As a candidate, I am available for the interview. "
                "Please confirm by 25 September 2025 between 10:00 and 12:00.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "meeting_date": "25 September 2025",
                    "deadline": "25 September 2025",
                },
            ),
            (
                "Hiring process enquiry for the analyst role",
                "Could you share the steps of the hiring process for the analyst role? "
                "I would like to know the expected timeline.",
                {"priority": "low", "sentiment": "neutral", "deadline": None},
            ),
        ],
        "general_information": [
            (
                "October newsletter - product updates",
                "For your information, the October newsletter is out with product updates and tips. "
                "This is an automated message, no reply needed.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Company all-hands announcement",
                "Hello everyone, this is an announcement about the company all-hands on 2025-10-03. "
                "Do not reply to this mailbox.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "FYI: office closed on Monday",
                "For your information the office will be closed on Monday for the public holiday. "
                "No reply is required.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Policy update for all staff",
                "Please be informed that the travel policy has been updated. "
                "The new version is available on the intranet.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": True,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Holiday schedule bulletin",
                "Bulletin: the holiday schedule for the next quarter has been published. "
                "This mailbox is not monitored, no reply needed.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "New employee handbook available",
                "Kindly note that the new employee handbook is now available. It replaces all previous versions.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": True,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Reminder: quarterly town hall",
                "For your information, the quarterly town hall takes place at the end of this month. "
                "Please register by the end of this month if you plan to attend.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": True,
                    "action_required": True,
                    "deadline": "end of this month",
                },
            ),
            (
                "Newsletter: five tips for better reports",
                "Our newsletter this week shares five tips for better reports. No reply needed.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Phone system upgrade notice",
                "Please be informed that the phone system will be upgraded this weekend. "
                "Calls may fail during the maintenance window.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": True,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Bulletin: parking lot maintenance",
                "Bulletin: the parking lot will be repainted next week. This is an informational update only.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": True,
                    "action_required": False,
                    "deadline": None,
                },
            ),
        ],
        "urgent": [
            (
                "URGENT: contract signature needed immediately",
                "URGENT: we need your signature on the contract immediately. Without it the deal cannot proceed today.",
                {
                    "priority": "critical",
                    "sentiment": "urgent",
                    "category_any_of": ["urgent", "sales_inquiry", "other"],
                    "deadline": None,
                },
            ),
            (
                "URGENT: response required within 24 hours",
                "URGENT: please send your response within 24 hours so we can close the case file. "
                "This request is time sensitive.",
                {
                    "priority": "high",
                    "sentiment": "urgent",
                    "category_any_of": ["urgent", "other"],
                    "deadline": "within 24 hours",
                },
            ),
            (
                "Critical security alert for all administrators",
                "Critical security alert: all administrators must review their access logs. "
                "This message requires immediate attention.",
                {
                    "priority": "critical",
                    "sentiment": "urgent",
                    "category_any_of": ["urgent", "support_request"],
                    "deadline": None,
                },
            ),
            (
                "ASAP: approval needed for the wire transfer",
                "ASAP: the client approval for the wire transfer has not arrived. Please respond as soon as possible.",
                {
                    "priority": "critical",
                    "sentiment": "urgent",
                    "category_any_of": ["urgent", "invoice_payment"],
                    "deadline": None,
                },
            ),
            (
                "Emergency: water leak in the office",
                "Emergency: there is a water leak near the server room. "
                "Please respond immediately so facilities can act.",
                {
                    "priority": "critical",
                    "sentiment": "urgent",
                    "category_any_of": ["urgent", "other"],
                    "deadline": None,
                },
            ),
            (
                "URGENT: delivery must leave today",
                "URGENT: order {order} must leave the warehouse today. Please confirm pickup right away.",
                {
                    "priority": "critical",
                    "sentiment": "urgent",
                    "category_any_of": ["urgent", "sales_inquiry"],
                    "order_number": "{order}",
                    "deadline": None,
                },
            ),
            (
                "Final notice: overdue account must be settled",
                "Final notice: your account is overdue and this is urgent. "
                "Please settle the amount by tomorrow before the service is suspended.",
                {
                    "priority": "high",
                    "sentiment": "urgent",
                    "category_any_of": ["invoice_payment", "urgent"],
                    "deadline": "by tomorrow",
                },
            ),
            (
                "Please respond immediately to this urgent query",
                "This is an urgent query from our operations desk. "
                "Please respond immediately with the confirmation number.",
                {
                    "priority": "critical",
                    "sentiment": "urgent",
                    "category_any_of": ["urgent", "other"],
                    "deadline": None,
                },
            ),
            (
                "URGENT: the client meeting starts in one hour",
                "URGENT: the client meeting starts in one hour and the agenda has not been shared. "
                "Please send it as soon as possible.",
                {
                    "priority": "high",
                    "sentiment": "urgent",
                    "category_any_of": ["meeting_request", "urgent"],
                    "deadline": None,
                },
            ),
            (
                "Right away: we need your confirmation",
                "Right away: we need your confirmation on the revised schedule. Production is waiting for your answer.",
                {
                    "priority": "critical",
                    "sentiment": "urgent",
                    "category_any_of": ["urgent", "other"],
                    "deadline": None,
                },
            ),
        ],
        "spam": [
            (
                "Congratulations, you are our lucky winner",
                "Congratulations you have won the international lottery draw. "
                "Click here now to claim your prize today.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Exclusive crypto profit opportunity",
                "Exclusive crypto profit opportunity: double your money in thirty days. "
                "Act now and click here now for free access.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Limited time offer - 80 percent off",
                "Limited time offer: 80 percent off every item in the store. "
                "Unsubscribe if you do not want to see this again.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "You have been selected for a prize draw",
                "You have been selected for a prize draw worth five thousand dollars. "
                "Reply with your details to receive your gift.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Double your money with this guaranteed scheme",
                "Double your money with this guaranteed investment scheme. "
                "Limited slots are available for early participants.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Flash sale: everything must go",
                "Flash sale: everything must go, prices slashed for today only. "
                "You can unsubscribe at any time using the link below.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Work from home and earn daily",
                "Work from home and earn daily with no experience required. "
                "Click here now to start this 100 percent free programme.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Congratulations you are the selected winner",
                "Congratulations you are the selected winner of our customer appreciation draw. "
                "Claim the prize now or the offer will be withdrawn.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "Exclusive deal for a limited time",
                "Exclusive deal for a limited time: an unbeatable bundle with free gifts. "
                "Unsubscribe from future offers in one click.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
            (
                "100 percent free trial - no obligations",
                "Claim your 100 percent free trial today. Click here now to activate while the window is open. "
                "This is a one time promotional offer.",
                {
                    "priority": "low",
                    "sentiment": "neutral",
                    "reply_required": False,
                    "action_required": False,
                    "deadline": None,
                },
            ),
        ],
    }


def _format(text: str, persona: dict, index: int) -> str:
    order = f"ORD-{73000 + index * 7}"
    amount = f"{29 + (index * 17) % 400}.99"
    return text.format(
        name=persona["name"],
        first=persona["first"],
        company=persona["company"],
        email=f"contact{index}@{persona['domain']}",
        order=order,
        amount=amount,
        currency="USD" if index % 3 else "EUR",
    )


def build_dataset() -> dict:
    entries = _entries()
    emails: list[dict] = []
    counter = 0
    for group in GROUPS:
        for _position, (subject_template, body_template, expected_template) in enumerate(entries[group]):
            persona = PERSONAS[counter % len(PERSONAS)]
            received_at = _received_at(counter)
            subject = _format(subject_template, persona, counter)
            body = _format(body_template, persona, counter)

            expected: dict = {"category": group}
            for key, value in expected_template.items():
                if key == "category_any_of":
                    expected["category_any_of"] = value
                elif key == "deadline":
                    if value is None:
                        expected["deadline_text"] = None
                        expected["due_date"] = None
                    else:
                        expected["deadline_text"] = value
                        due = _deadline_due(value, received_at)
                        expected["due_date"] = due.isoformat() if due else None
                elif key == "reply_required" or key == "action_required":
                    expected[key] = value
                elif key in {
                    "priority",
                    "sentiment",
                    "invoice_number",
                    "order_number",
                    "amount",
                    "currency",
                    "meeting_date",
                }:
                    expected[key] = (
                        _format(str(value), persona, counter) if isinstance(value, str) and "{" in str(value) else value
                    )
                elif key == "customer_name":
                    expected[key] = persona["name"]
                elif key == "company":
                    expected[key] = persona["company"]
                elif key == "location":
                    expected[key] = value
                else:
                    expected[key] = value

            # Defaults derived from the group when not stated explicitly.
            expected.setdefault("priority", "medium")
            expected.setdefault("sentiment", "neutral")
            if "reply_required" not in expected:
                expected["reply_required"] = group not in {"general_information", "spam"} or "no reply" in body.lower()
            if "action_required" not in expected:
                expected["action_required"] = group not in {"general_information", "spam"}
            expected.setdefault("invoice_number", None)
            expected.setdefault("order_number", None)
            # Fields that must NOT be invented for this email.
            absent = ["phone_number"]
            if expected.get("invoice_number") is None:
                absent.append("invoice_number")
            if expected.get("order_number") is None:
                absent.append("order_number")
            expected["must_be_absent"] = absent

            emails.append(
                {
                    "id": f"synthetic_{counter + 1:03d}",
                    "group": group,
                    "subject": subject,
                    "sender": f"{persona['name']} <{persona['name'].lower().replace(' ', '.')}@{persona['domain']}>",
                    "recipients": [STAFF],
                    "body": body,
                    "received_at": received_at.isoformat(),
                    "expected": expected,
                }
            )
            counter += 1

    return {
        "dataset_version": "1.0",
        "description": "Synthetic business emails with expected AI outcomes. All identities are fake.",
        "reference_timezone": "UTC",
        "group_counts": {group: sum(1 for email in emails if email["group"] == group) for group in GROUPS},
        "emails": emails,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic email dataset")
    parser.add_argument("--out", default="tests/fixtures/sample_emails.json")
    args = parser.parse_args()

    dataset = build_dataset()
    out_path = args.out
    from pathlib import Path

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(dataset['emails'])} emails to {out_path}")
    for group, count in dataset["group_counts"].items():
        print(f"  {group}: {count}")


if __name__ == "__main__":
    main()
