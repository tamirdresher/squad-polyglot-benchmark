FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV AIDER_DOCKER=1

# Base tools
RUN apt-get update && apt-get install -y \
    curl wget git build-essential cmake \
    software-properties-common ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python 3.11
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    && rm -rf /var/lib/apt/lists/*
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Go 1.22
RUN wget -q https://go.dev/dl/go1.22.4.linux-amd64.tar.gz && \
    tar -C /usr/local -xzf go1.22.4.linux-amd64.tar.gz && \
    rm go1.22.4.linux-amd64.tar.gz
ENV PATH="/usr/local/go/bin:${PATH}"

# Rust (latest stable)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Node.js 20 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Java 17 + Gradle
RUN apt-get update && apt-get install -y openjdk-17-jdk && \
    rm -rf /var/lib/apt/lists/*
RUN wget -q https://services.gradle.org/distributions/gradle-8.7-bin.zip && \
    unzip -q gradle-8.7-bin.zip -d /opt && \
    rm gradle-8.7-bin.zip
ENV PATH="/opt/gradle-8.7/bin:${PATH}"
ENV JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"

# Python test dependencies
RUN pip3 install pytest

# Working directory
WORKDIR /app

# Copy benchmark runner
COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . .

# Copy test scripts
COPY scripts/npm-test.sh /app/scripts/npm-test.sh
COPY scripts/cpp-test.sh /app/scripts/cpp-test.sh
RUN chmod +x /app/scripts/*.sh

CMD ["python", "runner.py", "--help"]
