"""Read RFQ emails: saved .eml files, Outlook .msg files, or pasted text.

    from src.read_email import read_email
    mail = read_email("enquiry.eml")
    mail["body"], mail["attachments"]      # text, [(filename, bytes), ...]

Everything runs locally (.eml uses Python's own email package, .msg uses
the extract-msg package).
"""

import re
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

from src.extract_rfq import (
    CURRENCY_RE,
    CURRENCY_SYMBOLS,
    EMAIL_RE,
    HEADER_FIELDS,
    PHONE_RES,
    clean,
    tidy_date,
)


class _TextFromHtml(HTMLParser):
    BREAKS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self.BREAKS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append("\t")          # keeps HTML tables as columns

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextFromHtml()
    parser.feed(html or "")
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \r\f\v]+", " ", line).strip(" ") for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _empty_mail():
    return {"subject": "", "sender_name": "", "sender_email": "", "date": "",
            "body": "", "attachments": []}


def read_eml(path) -> dict:
    with open(path, "rb") as handle:
        message = BytesParser(policy=policy.default).parse(handle)
    mail = _empty_mail()
    mail["subject"] = clean(message.get("subject", ""))
    senders = getaddresses([message.get("from", "")])
    if senders:
        mail["sender_name"], mail["sender_email"] = clean(senders[0][0]), senders[0][1]
    try:
        mail["date"] = parsedate_to_datetime(message.get("date")).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        mail["date"] = ""

    body = message.get_body(preferencelist=("plain", "html"))
    if body is not None:
        content = body.get_content()
        mail["body"] = html_to_text(content) if body.get_content_type() == "text/html" else content

    for part in message.iter_attachments():
        filename = part.get_filename()
        if filename:
            mail["attachments"].append((Path(filename).name, part.get_payload(decode=True) or b""))
    return mail


def read_msg(path) -> dict:
    try:
        import extract_msg
    except ImportError as error:
        raise RuntimeError("Reading Outlook .msg files needs: pip install extract-msg") from error

    message = extract_msg.openMsg(str(path))
    try:
        mail = _empty_mail()
        mail["subject"] = clean(message.subject or "")
        sender = message.sender or ""
        found = EMAIL_RE.search(sender)
        mail["sender_email"] = found.group(0) if found else ""
        mail["sender_name"] = clean(re.sub(r"<[^>]*>", "", sender).replace(mail["sender_email"], ""))
        try:
            mail["date"] = message.date.strftime("%d/%m/%Y") if message.date else ""
        except AttributeError:
            mail["date"] = ""
        body = message.body or ""
        if not body.strip() and getattr(message, "htmlBody", None):
            html = message.htmlBody
            body = html_to_text(html.decode("utf-8", "ignore") if isinstance(html, bytes) else html)
        mail["body"] = body
        for attachment in message.attachments:
            filename = getattr(attachment, "longFilename", None) or getattr(attachment, "shortFilename", None)
            data = getattr(attachment, "data", None)
            if filename and isinstance(data, bytes):
                mail["attachments"].append((Path(filename).name, data))
    finally:
        message.close()
    return mail


def read_text_file(path) -> dict:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    mail = _empty_mail()
    mail["body"] = text
    return mail


def read_email(path) -> dict:
    suffix = Path(path).suffix.lower()
    if suffix == ".eml":
        return read_eml(path)
    if suffix == ".msg":
        return read_msg(path)
    return read_text_file(path)


# ------------------------------------------------------------ RFQ header
RFQ_NO_RE = re.compile(
    r"\b(?:RFQ|RFP|enquiry|inquiry|tender|ref(?:erence)?)\s*(?:no\.?|number|#|ref\.?)?\s*[:#\-]?\s*"
    r"([A-Z0-9][A-Z0-9/\-_.]*\d[A-Z0-9/\-_.]*)",
    re.I,
)
DUE_RE = re.compile(
    r"\b(?:by|before|on or before|latest by|due(?:\s+date)?|closing date|deadline)\s*[:\-]?\s*"
    r"(\d{1,2}(?:st|nd|rd|th)?[\s/.-]+(?:[A-Za-z]{3,9}|\d{1,2})[\s/.,-]+\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
    re.I,
)
SUBJECT_PREFIX_RE = re.compile(r"^\s*(?:(?:re|fw|fwd|aw)\s*:\s*)+", re.I)
COMPANY_RE = re.compile(r"\b(?:ltd|limited|llp|llc|inc|plc|pvt|gmbh|co\.|company|corporation|"
                        r"engineers|engineering|services|industries|enterprises|solutions)\b", re.I)


def _signature(lines):
    """The lines after the sign-off ('Regards,' ...)."""
    from src.parse_free_text import SIGN_OFF_RE

    for i in range(len(lines) - 1, -1, -1):
        if SIGN_OFF_RE.match(lines[i]):
            return [clean(l) for l in lines[i + 1:i + 9] if clean(l)]
    return []


def header_from_text(body: str, subject: str = "", sender_name: str = "",
                     sender_email: str = "", date: str = "") -> dict:
    """Fill the RFQ header fields from an email (or pasted text)."""
    header = {key: "" for key, _ in HEADER_FIELDS}
    lines = (body or "").splitlines()
    # Only look at the newest message, not the quoted reply chain.
    from src.parse_free_text import strip_email_noise

    main, _ = strip_email_noise(lines)
    text = "\n".join(lines)
    main_text = "\n".join(main)
    signature = _signature(lines)
    signature_text = "\n".join(signature)

    header["email"] = sender_email or (EMAIL_RE.search(signature_text or text) or [""])[0]
    for pattern in PHONE_RES:
        match = pattern.search(signature_text) or pattern.search(text)
        if match:
            header["phone"] = clean(match.group(1))
            break

    # Contact = sender's name, else the first signature line.
    header["contact_person"] = sender_name or (signature[0] if signature else "")
    company = next((l for l in signature if COMPANY_RE.search(l) and not EMAIL_RE.search(l)), "")
    header["customer_name"] = company

    subject = SUBJECT_PREFIX_RE.sub("", subject or "")
    header["project"] = clean(subject)
    for source in (subject, main_text, text):
        match = RFQ_NO_RE.search(source or "")
        if match:
            header["rfq_number"] = match.group(1).rstrip(".-/")
            break

    header["rfq_date"] = date
    due = DUE_RE.search(main_text) or DUE_RE.search(text)
    if due:
        header["due_date"] = tidy_date(re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", due.group(1)))

    currency = CURRENCY_RE.search(text)
    if currency:
        header["currency"] = currency.group(1)
    else:
        header["currency"] = next((c for s, c in CURRENCY_SYMBOLS.items() if s in text), "")
    return header


def header_from_mail(mail: dict) -> dict:
    return header_from_text(mail["body"], mail["subject"], mail["sender_name"],
                            mail["sender_email"], mail["date"])
