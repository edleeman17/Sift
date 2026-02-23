"""Task commands: TODO, DONE."""

import logging
import os
from pathlib import Path

from commands import register_command

log = logging.getLogger(__name__)

OBSIDIAN_TODO = os.getenv("OBSIDIAN_TODO", os.path.expanduser("~/obsidian/_todo.md"))


@register_command("TODO")
async def handle_todo(args: str = "") -> str:
    """Add or read TODO items from Obsidian _todo.md file."""
    todo_file = Path(OBSIDIAN_TODO)

    # No task provided - read back TODOs
    if not args:
        try:
            if not todo_file.exists():
                return "No TODOs yet"

            content = todo_file.read_text()
            # Find uncompleted tasks (- [ ])
            uncompleted = [line.strip() for line in content.split("\n")
                          if line.strip().startswith("- [ ]")]

            if not uncompleted:
                return "All TODOs complete!"

            # Format for SMS - strip the "- [ ] " prefix, show all
            items = [item[6:] for item in uncompleted]
            result = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))

            return result

        except Exception as e:
            log.error(f"TODO read error: {e}")
            return f"Failed to read TODOs: {str(e)[:80]}"

    # Task provided - add it
    try:
        todo_line = f"- [ ] {args}\n"

        with open(todo_file, "a") as f:
            f.write(todo_line)

        log.info(f"Added TODO to {todo_file}: {args}")
        return f"Added: {args[:100]}"

    except Exception as e:
        log.error(f"TODO error: {e}")
        return f"Failed to add TODO: {str(e)[:80]}"


@register_command("DONE")
async def handle_done(args: str = "") -> str:
    """Mark TODO items as complete by their number."""
    todo_file = Path(OBSIDIAN_TODO)

    if not todo_file.exists():
        return "No TODOs to complete"

    # Parse numbers - accept "1,2,3" or "1 2 3" or just "1"
    try:
        nums = [int(n.strip()) for n in args.replace(",", " ").split()]
    except ValueError:
        return "Usage: DONE 1,2,3 or DONE 1 2 3"

    if not nums:
        return "Usage: DONE 1,2,3"

    try:
        content = todo_file.read_text()
        lines = content.split("\n")

        # Find uncompleted tasks and their line indices
        uncompleted = []
        for i, line in enumerate(lines):
            if line.strip().startswith("- [ ]"):
                uncompleted.append(i)

        completed_tasks = []
        for num in nums:
            if 1 <= num <= len(uncompleted):
                line_idx = uncompleted[num - 1]
                # Mark as done
                lines[line_idx] = lines[line_idx].replace("- [ ]", "- [x]", 1)
                task_text = lines[line_idx].replace("- [x]", "").strip()
                completed_tasks.append(task_text[:30])

        # Write back
        todo_file.write_text("\n".join(lines))

        if completed_tasks:
            return f"Done: {', '.join(completed_tasks)}"
        else:
            return f"Invalid numbers. You have {len(uncompleted)} TODOs."

    except Exception as e:
        log.error(f"DONE error: {e}")
        return f"Failed: {str(e)[:80]}"
