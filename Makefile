.PHONY: build up down logs test health pull-model setup-hooks

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f processor

test:
	curl -X POST http://localhost:8090/notification \
		-H "Content-Type: application/json" \
		-d '{"app": "discord", "title": "Uptime Kuma", "body": "Server X is down"}'

test-drop:
	curl -X POST http://localhost:8090/notification \
		-H "Content-Type: application/json" \
		-d '{"app": "discord", "title": "Random User", "body": "Hello world"}'

test-messages:
	curl -X POST http://localhost:8090/notification \
		-H "Content-Type: application/json" \
		-d '{"app": "messages", "title": "Friend", "body": "Hey, are you free?"}'

health:
	curl http://localhost:8090/health

pull-model:
	docker compose exec ollama ollama pull qwen2.5:7b

restart:
	docker compose restart processor

rebuild:
	docker compose up -d --build processor

setup-hooks:
	cp hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Git hooks installed"
