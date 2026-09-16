# SMTP Gateway

Sends outbound SMS to your dumbphone by emailing your iPhone instead of
scripting a Mac. Use this instead of `imessage-gateway/` if you don't have
a Mac to dedicate to it, or just don't want one running 24/7.

## Why this exists

The original gateway sends from your iPhone's real number by driving
Messages.app with AppleScript, which means a Mac has to be on and signed
in the whole time. This one skips the Mac entirely: it sends a plain
email, and an iOS Shortcut on the phone itself does the actual `Send
Message`. Same result (a real text from your number), no Mac required.

Both gateways speak the exact same contract as far as Sift is concerned -
`POST /send` with `{"recipient": ..., "message": ...}` - so switching
between them is just a config change (`imessage.gateway_url` in
`config.yaml`), nothing in the processor needs to know which one is
running.

## How it works

```
Processor → SMTP Gateway → Email → iPhone (push) → Shortcut → Send Message → Dumbphone
```

1. The processor POSTs a notification to this gateway.
2. The gateway emails it to your own inbox via SMTP.
3. A Shortcuts Personal Automation on your iPhone, watching for that
   email, fires the instant it arrives (push, not polling).
4. The Shortcut runs `Send Message` to your dumbphone - same as before,
   iMessage where possible, falling back to SMS automatically.

## Requirements

- Any SMTP account you can send from (a self-hosted mail server, or an
  existing provider that allows SMTP auth / app passwords).
- A receiving mail account on your iPhone with **push** enabled, not
  fetch/manual - this is what makes step 3 instant. iCloud Mail and Gmail
  both support this.

## Setup

### 1. Run the gateway

```bash
cp .env.example .env   # fill in your SMTP details
./run.sh
```

Or with Docker:

```bash
docker build -t smtp-gateway .
docker run -p 8095:8095 --env-file .env smtp-gateway
```

### 2. Point Sift at it

In `config.yaml`:

```yaml
sinks:
  imessage:
    enabled: true
    gateway_url: "http://localhost:8095"
    recipient: "+441234567890"   # kept for logging, not used to address the email
```

### 3. Create the Shortcut on your iPhone

1. Shortcuts app → new shortcut, name it something like
   `SendDumbphoneSMS`.
2. Add action **Send Message** - set the recipient to your dumbphone's
   number, and the message to **Shortcut Input**.
3. Go to the **Automation** tab → **+** → **Create Personal Automation**
   → **Email**.
4. Set the filter to match your setup: **Account** = the inbox
   `TO_ADDRESS` points at, **Subject Contains** = the value of `SUBJECT`
   (`SIFT-SMS` by default).
5. Action: **Run Shortcut** → `SendDumbphoneSMS`, with input set to the
   email's **Message Content** (or **Subject**, if you'd rather send that -
   whichever the earlier `Send Message` action expects as its input).
6. Turn **off** "Ask Before Running" and set the automation to **Run
   Immediately**, not "Ask" - otherwise every notification pops a
   confirmation instead of sending silently.

### 4. Test it

```bash
curl -X POST http://localhost:8095/send \
  -H 'Content-Type: application/json' \
  -d '{"recipient": "+441234567890", "message": "test"}'
```

You should get a text on the dumbphone within a few seconds. If nothing
arrives, check the email actually landed in the right account first
(rules out the SMTP half), then check the automation is set to Run
Immediately with Ask Before Running off (rules out the Shortcut half).

## Notes

- The `SUBJECT` filter has to match exactly between `.env` and the
  Shortcuts automation. If you change one, change the other - a mismatch
  fails silently, the automation just never fires.
- This gateway doesn't need to run on the same machine as the processor.
  Anywhere on your network (or the internet, if you add auth in front of
  it) that can reach an SMTP server works.
