"""Help command: HELP [command]."""

import logging
from typing import Optional

from commands import register_command, COMMAND_REGISTRY

log = logging.getLogger(__name__)

# Short descriptions for command list (extracted from docstrings or manual)
COMMAND_SUMMARIES = {
    "PING": "Check Pi + iPhone status",
    "RESET": "Restart BLE stack on Pi",
    "LOCATE": "Sound alarm on iPhone",
    "EMERGENCY": "Toggle emergency mode",
    "WEATHER": "Current weather or forecast",
    "RAIN": "Rain forecast",
    "TODO": "List or add tasks",
    "DONE": "Mark tasks complete",
    "BIN": "Which bin this week",
    "ICE": "Emergency info",
    "INSURANCE": "Car insurance details",
    "BRIEFING": "Morning summary",
    "CALL": "Look up contact phone",
    "CONTACT": "Business lookup",
    "MESSAGES": "Summarize unread messages",
    "NAV": "Directions",
    "TIMER": "Set countdown timer",
    "REMIND": "Set reminder",
    "SEARCH": "Web search",
    "BORED": "Activity suggestion",
    "RINGGO": "Parking (start/extend)",
}


def get_command_help(command: str) -> Optional[str]:
    """Get detailed help for a command from its docstring."""
    handler = COMMAND_REGISTRY.get(command.upper())
    if not handler:
        return None

    doc = handler.__doc__
    if not doc:
        return f"{command.upper()}: No documentation available"

    # Clean up docstring - get first paragraph and usage
    lines = doc.strip().split("\n")
    result = []

    for line in lines:
        stripped = line.strip()
        # Stop at Examples section (too verbose for SMS)
        if stripped.lower().startswith("examples:"):
            break
        if stripped.lower().startswith("configure"):
            break
        result.append(stripped)

    return "\n".join(result).strip()


@register_command("HELP")
async def handle_help(args: str = "") -> str:
    """Get help on available commands.

    Usage:
        HELP            List all commands
        HELP [command]  Details for specific command

    Examples:
        HELP
        HELP RINGGO
        HELP WEATHER
    """
    args = args.strip().upper()

    if args:
        # Help for specific command
        help_text = get_command_help(args)
        if help_text:
            return help_text
        return f"Unknown command: {args}"

    # List all commands
    commands = sorted(COMMAND_REGISTRY.keys())

    # Group into lines with summaries
    lines = []
    for cmd in commands:
        summary = COMMAND_SUMMARIES.get(cmd, "")
        if summary:
            lines.append(f"{cmd} - {summary}")
        else:
            lines.append(cmd)

    return "Commands:\n" + "\n".join(lines) + "\n\nHELP [cmd] for details"
