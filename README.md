:::writing{variant=standard id=73952}

Sift

🧠 Forward only the notifications that matter.

Sift is a self-hosted filter that captures iOS notifications and forwards only the important ones via SMS or push.

Built for people who want the benefits of a smartphone without the noise.

⸻

✨ Why Sift

Modern phones are excellent at one thing: interrupting you.

Sift lets you:
	•	📵 Carry a simpler phone day-to-day
	•	🚨 Stay reachable for genuine emergencies
	•	🔐 Receive critical 2FA codes
	•	🧘 Reduce notification anxiety
	•	🏠 Keep everything self-hosted

You decide what gets through.

⸻

🏗️ Architecture

flowchart LR
    iPhone -->|BLE capture| Sift
    Sift --> Filter
    Filter --> SMS
    Filter --> Push
    Filter --> iMessage

Capture → filter → forward.

⸻

🚀 Quick Start

git clone https://github.com/edleeman17/sift.git
cd sift

cp config.example.yaml config.yaml
cp docker-compose.example.yaml docker-compose.yaml

docker compose up -d

Then open:

👉 http://localhost:8090

⸻

🧠 Core Features
	•	Intelligent notification filtering
	•	SMS forwarding
	•	Optional push notifications
	•	Optional iMessage relay
	•	Web dashboard for rule management
	•	Fully self-hosted
	•	Docker-first deployment

Minimal by design. Powerful when needed.

⸻

👤 Who This Is For

Sift is ideal if you:
	•	Practice digital minimalism
	•	Want fewer interruptions
	•	Need emergency reachability
	•	Run a home lab or self-hosted stack

Not ideal if you:
	•	Need guaranteed real-time delivery
	•	Want a fully managed cloud service
	•	Don’t have basic self-hosting experience

⸻

⚠️ Project Status

Experimental — functional but evolving.

Expect rough edges. Contributions welcome.

⸻

🤝 Contributing

PRs, issues, and experiments are welcome.

If you’re building tools for calmer computing, you’re in the right place.

⸻

📜 License

MIT
:::