# Security Policy

## Reporting a Vulnerability

If you find a security issue, please [open a GitHub issue](https://github.com/edleeman17/sift/issues/new) with the label "security". If it's sensitive, mention that in the issue and I'll reach out privately.

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes

I'll acknowledge within 48 hours and aim to fix critical issues within a week.

## Security Considerations

This project handles potentially sensitive data (notification content, phone numbers, contacts). Some things to be aware of:

### Credentials

- **Never commit** `config.yaml`, `contacts.json`, or `docker-compose.yaml` - they contain API keys and personal data
- Use the `.example` files as templates
- The `.gitignore` is configured to exclude these, but check before pushing

### Network

- The processor listens on port 8090 by default - don't expose this to the internet without authentication
- Communication between Pi and processor is unencrypted HTTP - keep on local network or use a VPN
- Ollama API is also unencrypted

### Data Storage

- Notifications are stored in SQLite (`data/notifications.db`) including message content
- Consider this when backing up or sharing the database
- The SMS assistant state file tracks message IDs

### Third-Party Services

- Twilio, Bark, ntfy all receive your notification content
- Review their privacy policies if that's a concern
- Console sink is the only option that keeps data fully local

## Supported Versions

This is a personal project without formal version support. I'll fix security issues in the latest version on main.
