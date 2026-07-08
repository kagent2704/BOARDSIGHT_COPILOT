FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONIOENCODING=UTF-8
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV MPLBACKEND=Agg
ENV HF_HOME=/workspace/.cache/huggingface
ENV TF_CPP_MIN_LOG_LEVEL=2
ENV HF_HUB_DISABLE_SYMLINKS_WARNING=1
ENV BOARDSIGHT_WARM_MODELS=0

WORKDIR /workspace/python-ai

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        liblapack-dev \
        libopenblas-dev \
        libsm6 \
        libxext6 \
        libxrender1 \
        wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-core.txt requirements-runtime.txt ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements-core.txt -r requirements-runtime.txt

COPY . /workspace/python-ai

RUN mkdir -p /workspace/output /workspace/.cache/huggingface

EXPOSE 8000

CMD ["python", "boardsight_ai/service.py", "--host", "0.0.0.0", "--port", "8000"]
