#!/usr/bin/env python3
"""SMTP Gateway - HTTP server that delivers SMS via email + an iOS Shortcut.

Drop-in alternative to imessage-gateway/. Both speak the same contract
Sift's processor/sinks/imessage_sink.py expects: POST /send with
{"recipient": ..., "message": ...}, 200 back on success. Point the same
`imessage.gateway_url` config at whichever one you run.

Why this exists: the original imessage-gateway needs a Mac running
Messages.app 24/7 to fire AppleScript. If you don't have a spare Mac (or
don't want to keep one awake for this), this gateway needs nothing but a
place to send an email from. It sends a plain email to your own iPhone's
inbox, and a Shortcuts Personal Automation on the phone (trigger: Email
received, Run Immediately, Ask Before Running off) catches it and runs a
`Send Message` to your dumbphone. No Mac, no third-party automation
service, no spare device - just SMTP and a push-capable mail account
(iCloud Mail's native push is what makes "Run Immediately" fire instantly
instead of waiting on a poll interval; most other providers with IMAP IDLE
push should work the same way).

Any SMTP account works - a self-hosted mail server, or your existing
provider. See README.md in this directory for the full setup, including
the Shortcuts automation.

Config (env vars, see .env.example):
  SMTP_HOST      - your mail server's hostname
  SMTP_PORT      - defaults to 587 (STARTTLS)
  SMTP_USERNAME  - account to send from
  SMTP_PASSWORD  - that account's password
  TO_ADDRESS     - the inbox your Shortcuts automation watches
  SUBJECT        - defaults to "SIFT-SMS" - must stay in sync with the
                   Shortcuts automation's Subject Contains filter, or
                   delivery silently stops (the automation just never
                   matches)
  PORT           - defaults to 8095 (imessage-gateway's old port, so it's
                   a drop-in swap if you're migrating from it)
"""
import json
import logging
import os
import smtplib
import sys
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("smtp-gateway")

SMTP_HOST = os.environ["SMTP_HOST"]
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USERNAME = os.environ["SMTP_USERNAME"]
SMTP_PASSWORD = os.environ["SMTP_PASSWORD"]
TO_ADDRESS = os.environ["TO_ADDRESS"]
SUBJECT = os.environ.get("SUBJECT", "SIFT-SMS")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "smtp-gateway"}')
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/send":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        message = body.get("message", "")
        recipient = body.get("recipient", "")
        if not message:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"missing 'message'")
            return

        # recipient isn't used to address the email - the dumbphone number
        # is set once, on the phone, inside the Shortcut itself. Logged here
        # only for parity with the request shape imessage_sink.py sends.
        log.info("relaying to %s: %s", recipient, message[:80])

        mime = MIMEText(message)
        mime["Subject"] = SUBJECT
        mime["From"] = SMTP_USERNAME
        mime["To"] = TO_ADDRESS

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.sendmail(SMTP_USERNAME, [TO_ADDRESS], mime.as_string())
            ok = True
        except Exception as e:
            log.error("smtp send failed: %s", e)
            ok = False

        self.send_response(200 if ok else 502)
        self.end_headers()


def main():
    port = int(os.environ.get("PORT", 8095))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log.info("smtp-gateway listening on :%d", port)
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
