FROM python:3.12-slim

WORKDIR /app

# openssh-client - RESET (commands/system.py) shells out to `ssh`, not in
# this base image by default.
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8091

CMD ["python3", "assistant.py"]
