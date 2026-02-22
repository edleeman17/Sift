"""SMS Assistant command handlers.

Commands are organized by category:
- system: PING, RESET, LOCATE
- weather: WEATHER, RAIN
- todo: TODO, DONE
- info: BIN, ICE, INSURANCE, BRIEFING
- comms: CALL, CONTACT, MESSAGES
- utility: NAV, TIMER, REMIND, SEARCH, BORED

Each command handler is an async function that takes optional args and returns a string response.
"""

# Command registry - maps command names to handler functions
# Populated by register_command decorator or manual registration
COMMAND_REGISTRY: dict[str, callable] = {}


def register_command(name: str):
    """Decorator to register a command handler."""
    def decorator(func):
        COMMAND_REGISTRY[name.upper()] = func
        return func
    return decorator


def get_command_handler(name: str):
    """Get a command handler by name."""
    return COMMAND_REGISTRY.get(name.upper())


def list_commands() -> list[str]:
    """List all registered commands."""
    return sorted(COMMAND_REGISTRY.keys())
