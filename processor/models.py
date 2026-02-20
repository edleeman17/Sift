import re
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class NotificationRequest(BaseModel):
    """Incoming notification from iOS shortcut."""
    app: str
    title: str
    body: str
    timestamp: Optional[datetime] = None


class NotificationResponse(BaseModel):
    """Response to notification request."""
    status: str  # sent, dropped, rate_limited
    reason: str


# Phone number regex - matches UK and international formats
PHONE_PATTERN = re.compile(
    r'(?:\+44\s?|0)(?:\d\s?){9,10}|'  # UK: +44 or 0 followed by digits
    r'\+\d{1,3}\s?\d{6,14}|'           # International: +X followed by digits
    r'(?<!\d)\d{10,11}(?!\d)'          # Plain 10-11 digits
)

# Load contacts mapping
CONTACTS: dict[str, str] = {}
_contacts_path = Path("/app/contacts.json")
if _contacts_path.exists():
    try:
        CONTACTS = json.loads(_contacts_path.read_text())
        print(f"[contacts] Loaded {len(CONTACTS)} contacts")
    except Exception as e:
        print(f"[contacts] Failed to load: {e}")


def lookup_contact(name: str) -> Optional[str]:
    """Look up phone number by contact name (case-insensitive partial match)."""
    if not name or not CONTACTS:
        return None
    name_lower = name.lower()
    # Exact match first
    for contact, number in CONTACTS.items():
        if contact.lower() == name_lower:
            return number
    # Partial match (contact name contains the search name)
    for contact, number in CONTACTS.items():
        if name_lower in contact.lower():
            return number
    return None


def extract_phone_number(text: str) -> Optional[str]:
    """Extract first phone number from text, normalized for tel: URL."""
    if not text:
        return None
    match = PHONE_PATTERN.search(text)
    if match:
        # Normalize: remove spaces, ensure + prefix for international
        number = re.sub(r'\s', '', match.group())
        if number.startswith('0') and len(number) == 11:
            # UK number starting with 0 -> +44
            number = '+44' + number[1:]
        elif not number.startswith('+'):
            # Assume UK if no prefix
            number = '+44' + number
        return number
    return None


@dataclass
class Message:
    """Internal message representation."""
    app: str
    title: str
    body: str
    timestamp: datetime
    id: Optional[int] = None
    action: str = "pending"  # pending, sent, dropped, rate_limited
    reason: str = ""
    action_url: Optional[str] = None  # tel: or sms: URL for actions
    priority: str = "default"  # default, high, critical

    @classmethod
    def from_request(cls, req: NotificationRequest) -> "Message":
        msg = cls(
            app=req.app.lower(),
            title=req.title,
            body=req.body,
            timestamp=req.timestamp or datetime.utcnow(),
        )
        # Extract phone number and set action URL for phone/messages
        if msg.app in ('phone', 'messages', 'facetime'):
            # Try to extract number from text first
            number = extract_phone_number(msg.title) or extract_phone_number(msg.body)
            # Fall back to contact lookup
            if not number:
                number = lookup_contact(msg.title)
            if number:
                if msg.app == 'phone':
                    msg.action_url = f"tel:{number}"
                else:
                    msg.action_url = f"sms:{number}"
        return msg
