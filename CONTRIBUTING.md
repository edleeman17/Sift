# Contributing

Thanks for considering contributing. Here's how to get involved.

## Bug Reports

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your setup (iOS version, Pi model, Docker version, etc.)

## Feature Requests

Open an issue describing:
- What problem you're trying to solve
- How you'd like it to work
- Any alternatives you've considered

## Pull Requests

1. Fork the repo
2. Create a branch (`git checkout -b my-feature`)
3. Make your changes
4. Test locally with `make rebuild && make test`
5. Commit with a clear message
6. Push and open a PR

### Code Style

- Python: Keep it readable, no need for strict PEP8
- Use type hints where they add clarity
- Add comments for non-obvious logic
- Don't over-engineer - simple is better

### Adding a Sink

The most common contribution. See `processor/sinks/console_sink.py` for the simplest example:

1. Create `processor/sinks/your_sink.py` implementing `NotificationSink`
2. Export it in `processor/sinks/__init__.py`
3. Initialize in `main.py` lifespan function
4. Add config section to `config.example.yaml`
5. Document in README

### Adding an SMS Command

For the SMS assistant:

1. Add handler function in `sms-assistant/assistant.py`
2. Add to command dispatch in `process_message()`
3. Keep responses under 160 chars when possible (SMS limit)
4. Test with `echo "YOURCOMMAND" | python assistant.py --test`

## Development Setup

```bash
# Clone
git clone https://github.com/edleeman17/sift.git
cd sift

# Copy config
cp config.example.yaml config.yaml
cp docker-compose.example.yaml docker-compose.yaml

# Edit config.yaml with test credentials

# Run with rebuild on changes
make rebuild && make logs
```

## Questions?

Open an issue or start a discussion. No question is too basic.
