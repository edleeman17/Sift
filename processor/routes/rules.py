"""Rules management routes."""

import os
from pathlib import Path

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from rules import RuleEngine
from templates.rules import RULES_HTML

router = APIRouter(tags=["rules"])

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "/app/config.yaml"))

MATCHERS = [
    "sender_contains", "body_contains",
    "sender_not_contains", "body_not_contains",
    "contains", "channel_contains",
    "sender_regex", "body_regex", "regex"
]


@router.get("/rules", response_class=HTMLResponse)
async def rules_page():
    """Rules management page."""
    return HTMLResponse(content=RULES_HTML)


@router.get("/api/rules")
async def get_rules(request: Request):
    """Get all rules from config."""
    app = request.app
    rules_list = []

    # Global rules first
    for i, rule in enumerate(app.state.rules.global_rules):
        action = rule.get("action", "send")
        for matcher in MATCHERS:
            if matcher in rule:
                rules_list.append({
                    "app": "__global__",
                    "type": "global",
                    "index": i,
                    "action": action,
                    "matcher": matcher,
                    "value": rule[matcher],
                    "priority": rule.get("priority"),
                    "prompt": rule.get("prompt"),
                })
                break

    # App-specific rules
    for app_name, app_config in app.state.rules.apps.items():
        default_action = app_config.get("default", "drop")
        rules_list.append({
            "app": app_name,
            "type": "default",
            "action": default_action,
            "matcher": None,
            "value": None,
        })
        for i, rule in enumerate(app_config.get("rules", [])):
            action = rule.get("action", "send")
            for matcher in MATCHERS:
                if matcher in rule:
                    rules_list.append({
                        "app": app_name,
                        "type": "rule",
                        "index": i,
                        "action": action,
                        "matcher": matcher,
                        "value": rule[matcher],
                        "priority": rule.get("priority"),
                        "prompt": rule.get("prompt"),
                    })
                    break

    return {
        "rules": rules_list,
        "unknown_apps": app.state.rules.global_config.get("unknown_apps", "drop"),
        "matchers": MATCHERS
    }


@router.post("/api/rules")
async def add_rule(request: Request):
    """Add a new rule to config."""
    app = request.app
    data = await request.json()
    app_name = data.get("app", "").lower()
    matcher = data.get("matcher", "")
    value = data.get("value", "")
    action = data.get("action", "send")
    priority = data.get("priority")
    prompt = data.get("prompt")

    if not all([matcher, value, action]):
        return {"error": "Missing required fields"}

    if not app_name and app_name != "__global__":
        return {"error": "App is required"}

    # Read current config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    # Build the new rule
    new_rule = {matcher: value, "action": action}
    if priority:
        new_rule["priority"] = priority
    if prompt:
        new_rule["prompt"] = prompt

    if app_name == "__global__":
        # Add to global rules
        if "global" not in config:
            config["global"] = {}
        if "rules" not in config["global"]:
            config["global"]["rules"] = []
        config["global"]["rules"].append(new_rule)
    else:
        # Add to app-specific rules
        if "apps" not in config:
            config["apps"] = {}
        if app_name not in config["apps"]:
            config["apps"][app_name] = {"default": "drop", "rules": []}
        if "rules" not in config["apps"][app_name]:
            config["apps"][app_name]["rules"] = []
        config["apps"][app_name]["rules"].append(new_rule)

    # Write config
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Reload rules
    app.state.rules = RuleEngine(CONFIG_PATH)

    return {"status": "ok"}


@router.delete("/api/rules")
async def delete_rule(request: Request):
    """Delete a rule from config."""
    app = request.app
    data = await request.json()
    app_name = data.get("app", "").lower()
    index = data.get("index")

    if not app_name or index is None:
        return {"error": "Missing app or index"}

    # Read current config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    if app_name == "__global__":
        # Delete global rule
        if "global" not in config or "rules" not in config["global"]:
            return {"error": "No global rules found"}
        rules = config["global"]["rules"]
        if index < 0 or index >= len(rules):
            return {"error": f"Rule index {index} out of range"}
        rules.pop(index)
    else:
        # Delete app-specific rule
        if "apps" not in config or app_name not in config["apps"]:
            return {"error": f"App '{app_name}' not found"}
        rules = config["apps"][app_name].get("rules", [])
        if index < 0 or index >= len(rules):
            return {"error": f"Rule index {index} out of range"}
        rules.pop(index)

    # Write config
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Reload rules
    app.state.rules = RuleEngine(CONFIG_PATH)

    return {"status": "ok"}


@router.post("/api/rules/default")
async def set_default_action(request: Request):
    """Set default action for an app."""
    app = request.app
    data = await request.json()
    app_name = data.get("app", "").lower()
    action = data.get("action", "")

    if not app_name or action not in ["send", "drop"]:
        return {"error": "Invalid app or action"}

    # Read current config
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    # Ensure apps section exists
    if "apps" not in config:
        config["apps"] = {}

    # Ensure app exists
    if app_name not in config["apps"]:
        config["apps"][app_name] = {"default": action, "rules": []}
    else:
        config["apps"][app_name]["default"] = action

    # Write config
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Reload rules
    app.state.rules = RuleEngine(CONFIG_PATH)

    return {"status": "ok"}
