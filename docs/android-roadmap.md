# Android Version Roadmap

The iOS version relies on ANCS (Apple Notification Center Service) over Bluetooth, which requires a Raspberry Pi acting as a bridge. Android is much simpler - we can access notifications directly with a NotificationListenerService.

## Why Android is Easier

| iOS | Android |
|-----|---------|
| No API access to notifications | NotificationListenerService API |
| Requires BLE + external device (Pi) | Runs directly on device |
| Must be in Bluetooth range | Works anywhere with internet |
| Complex pairing process | Just grant permission |

## Architecture

```
Android App
├── NotificationListenerService  # Captures all notifications
├── RuleEngine                   # Same YAML config format
├── RateLimiter                  # Same deduplication logic
└── Sinks
    ├── HTTP POST               # Send to existing processor
    ├── ntfy (direct)           # Or send directly to ntfy
    └── Local storage           # For dashboard/history
```

### Option A: Thin Client

Android app captures notifications and POSTs to existing processor. Reuses all filtering logic.

```
Android → HTTP POST → Processor (Docker) → Sinks
```

Pros:
- Minimal Android code
- Single source of truth for rules
- Works with existing setup

Cons:
- Requires processor running somewhere
- Needs network connectivity to home

### Option B: Standalone App

Android app does everything locally. No server needed.

```
Android → Local RuleEngine → Direct to ntfy/Bark
```

Pros:
- Self-contained
- Works without home server
- Lower latency

Cons:
- Rules managed on device
- Need to reimplement logic in Kotlin

### Recommendation: Option A first

Start with thin client. Most users doing this experiment already have the processor running. Later add standalone mode as optional.

## Implementation Plan

### Phase 1: Basic Capture (MVP)

1. **NotificationListenerService** - Capture notifications
   - Request `BIND_NOTIFICATION_LISTENER_SERVICE` permission
   - Filter out system notifications (charging, screenshots, etc.)
   - Extract: app name, title, body, timestamp

2. **HTTP Client** - POST to processor
   - Same JSON format as ancs-bridge
   - Retry with exponential backoff
   - Queue when offline

3. **Settings UI**
   - Processor URL configuration
   - Enable/disable per app (basic filtering)
   - Connection status indicator

### Phase 2: Enhanced Features

4. **Local rule evaluation** - Filter before sending
   - Parse config.yaml format
   - Evaluate rules client-side
   - Reduce traffic to processor

5. **Battery optimization**
   - Batch notifications
   - Respect Doze mode
   - Option for immediate vs batched

6. **Offline mode**
   - SQLite queue for offline notifications
   - Sync when back online

### Phase 3: Standalone Mode

7. **Direct sink support**
   - ntfy integration
   - Bark integration
   - SMS via default SMS app

8. **Local dashboard**
   - Notification history
   - Stats and graphs
   - Rule management UI

## Technical Details

### NotificationListenerService

```kotlin
class NotificationCapture : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val notification = sbn.notification
        val extras = notification.extras

        val data = NotificationData(
            app = sbn.packageName,
            title = extras.getString(Notification.EXTRA_TITLE) ?: "",
            body = extras.getString(Notification.EXTRA_TEXT) ?: "",
            timestamp = sbn.postTime
        )

        // Send to processor or evaluate locally
    }
}
```

### Permission Request

Users must manually enable in Settings > Apps > Special access > Notification access. Can't be granted programmatically for security reasons.

### Filtering System Apps

Skip notifications from:
- `android` (system)
- `com.android.systemui`
- `com.android.providers.*`
- Any app in user-defined blocklist

### Message Format

Same as iOS version for compatibility:

```json
{
  "app": "com.whatsapp",
  "title": "John",
  "body": "Hey, are you free?",
  "timestamp": "2024-02-20T10:30:00Z"
}
```

## Dependencies

Minimal:
- Kotlin coroutines (async HTTP)
- Ktor or OkHttp (networking)
- Room (local SQLite, for queue/history)
- DataStore (preferences)

## Open Questions

1. **Which Android versions to support?**
   - NotificationListenerService available since API 18 (4.3)
   - Suggest API 26+ (8.0) for modern features

2. **Should we support Wear OS?**
   - Could be interesting for standalone forwarding
   - Lower priority

3. **F-Droid distribution?**
   - No Google dependencies in core
   - Could publish there for privacy-conscious users

## Contributing

If you're an Android developer interested in this, open an issue to discuss. Happy to collaborate on architecture decisions before diving into code.
