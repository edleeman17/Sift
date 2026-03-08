#!/usr/bin/env python3
"""Sync contacts from macOS Contacts.app to contacts.json.

Uses the Contacts framework via pyobjc. Install dependencies with:
    pip3 install pyobjc-framework-Contacts

Run manually:
    python3 scripts/sync_contacts.py

Or install the launchd plist for daily auto-sync.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def normalize_phone(phone: str) -> Optional[str]:
    """Normalize phone number to +XX format."""
    if not phone:
        return None
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone)
    if not cleaned:
        return None
    # UK number starting with 0 -> +44
    if cleaned.startswith('0') and len(cleaned) == 11:
        cleaned = '+44' + cleaned[1:]
    # Add + if missing (assume international)
    elif not cleaned.startswith('+'):
        if len(cleaned) == 10:
            cleaned = '+44' + cleaned  # Assume UK
        else:
            cleaned = '+' + cleaned
    return cleaned


def sync_contacts():
    """Sync contacts from macOS Contacts.app to contacts.json."""
    try:
        import Contacts
    except ImportError:
        print("ERROR: pyobjc-framework-Contacts not installed")
        print("Install with: pip3 install pyobjc-framework-Contacts")
        return 1

    # Request access to contacts
    store = Contacts.CNContactStore.alloc().init()

    # Check authorization status
    auth_status = Contacts.CNContactStore.authorizationStatusForEntityType_(
        Contacts.CNEntityTypeContacts
    )

    # Request access if not determined
    if auth_status == Contacts.CNAuthorizationStatusNotDetermined:
        print("Requesting Contacts access...")
        import threading
        event = threading.Event()
        granted = [False]

        def handler(success, error):
            granted[0] = success
            event.set()

        store.requestAccessForEntityType_completionHandler_(
            Contacts.CNEntityTypeContacts, handler
        )
        event.wait(timeout=30)
        if not granted[0]:
            print("ERROR: Contacts access denied")
            return 1
        auth_status = Contacts.CNAuthorizationStatusAuthorized

    if auth_status != Contacts.CNAuthorizationStatusAuthorized:
        print("ERROR: Contacts access not authorized")
        print("Grant access in System Preferences > Security & Privacy > Privacy > Contacts")
        return 1

    # Keys to fetch
    keys = [
        Contacts.CNContactGivenNameKey,
        Contacts.CNContactFamilyNameKey,
        Contacts.CNContactOrganizationNameKey,
        Contacts.CNContactPhoneNumbersKey,
    ]

    # Fetch all contacts
    request = Contacts.CNContactFetchRequest.alloc().initWithKeysToFetch_(keys)
    contacts_list = []

    def handler(contact, stop):
        contacts_list.append(contact)

    error = None
    success, error = store.enumerateContactsWithFetchRequest_error_usingBlock_(
        request, None, handler
    )

    if not success:
        print(f"ERROR: Failed to fetch contacts: {error}")
        return 1

    # Build contacts dict
    contacts = {}
    for contact in contacts_list:
        # Build name
        given = contact.givenName() or ""
        family = contact.familyName() or ""
        org = contact.organizationName() or ""

        if given or family:
            name = f"{given} {family}".strip()
        elif org:
            name = org
        else:
            continue  # Skip contacts without name

        # Get phone numbers
        phones = contact.phoneNumbers()
        if not phones or len(phones) == 0:
            continue  # Skip contacts without phone numbers

        # Use first phone number (normalized)
        phone_value = phones[0].value()
        phone = normalize_phone(phone_value.stringValue())
        if phone:
            contacts[name] = phone

    # Load existing contacts.json
    contacts_path = Path(__file__).parent.parent / "contacts.json"
    existing = {}
    if contacts_path.exists():
        try:
            existing = json.loads(contacts_path.read_text())
        except Exception as e:
            print(f"WARNING: Could not load existing contacts.json: {e}")

    # Merge: new contacts override, but keep entries not in Contacts.app
    merged = existing.copy()
    added = []
    updated = []
    for name, phone in contacts.items():
        if name not in merged:
            added.append(name)
        elif merged[name] != phone:
            updated.append(name)
        merged[name] = phone

    # Write merged contacts
    contacts_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False))

    # Summary
    print(f"[{datetime.now().isoformat()}] Contacts sync complete")
    print(f"  Total in Contacts.app: {len(contacts)}")
    print(f"  Added: {len(added)}")
    print(f"  Updated: {len(updated)}")
    print(f"  Total in contacts.json: {len(merged)}")

    if added:
        print(f"  New contacts: {', '.join(added[:5])}{'...' if len(added) > 5 else ''}")
    if updated:
        print(f"  Updated: {', '.join(updated[:5])}{'...' if len(updated) > 5 else ''}")

    return 0


if __name__ == "__main__":
    sys.exit(sync_contacts())
