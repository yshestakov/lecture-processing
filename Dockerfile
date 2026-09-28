# Lecture → Markdown toolbox: ffmpeg, faster-whisper, PySceneDetect and the pipeline scripts.
#
#   docker build -t lecture-tools .                       # tools only (default)
#   docker build -t lecture-agent --target agent .        # + Node, Pi and OpenCode, skill preinstalled
#   docker build -t lecture-tools --build-arg VAAPI=1 .   # + Intel/AMD VA-API drivers for h264_vaapi
#
# Run with ./docker-run.sh (mounts the current directory at /work and caches models in a volume).

ARG PYTHON_VERSION=3.12

############################ tools ############################
FROM python:${PYTHON_VERSION}-slim-bookworm AS tools

ARG VAAPI=0
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    HOME=/home/lecture \
    PATH=/opt/process/scripts:$PATH

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 ca-certificates curl bash \
 && if [ "$VAAPI" = "1" ]; then \
      apt-get install -y --no-install-recommends intel-media-va-driver mesa-va-drivers vainfo; \
    fi \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /opt/process/requirements.txt
RUN pip install -r /opt/process/requirements.txt

COPY scripts/ /opt/process/scripts/
COPY skills/ /opt/process/skills/
COPY AGENTS.md process.md pipeline.svg /opt/process/
RUN chmod +x /opt/process/scripts/*.sh /opt/process/scripts/*.py \
 && useradd -m -u 1000 -s /bin/bash lecture \
 && mkdir -p /models /work \
 && chmod 777 /models /work /home/lecture

WORKDIR /work
CMD ["bash"]

############################ agent ############################
# Optional layer: a coding agent that can run the LLM steps (Q & A digest, topics notes)
# inside the same container. Both Pi and OpenCode read skills from ~/.agents/skills/.
FROM tools AS agent

ARG NODE_MAJOR=22
ARG AGENT_PACKAGES="@mariozechner/pi-coding-agent opencode-ai"

RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
 && apt-get install -y --no-install-recommends nodejs git ripgrep \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g ${AGENT_PACKAGES} \
 && npm cache clean --force

# Skill + global conventions for both agents
RUN mkdir -p $HOME/.agents/skills $HOME/.pi/agent $HOME/.config/opencode \
 && cp -r /opt/process/skills/* $HOME/.agents/skills/ \
 && cp /opt/process/AGENTS.md $HOME/.pi/agent/AGENTS.md \
 && cp /opt/process/AGENTS.md $HOME/.config/opencode/AGENTS.md \
 && chmod -R a+rwX $HOME

# API keys come from the environment at run time (see docker-run.sh), never baked in.
CMD ["bash"]

############################ default ############################
FROM tools AS default
