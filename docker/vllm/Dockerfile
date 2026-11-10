FROM vllm/vllm-openai-cpu:latest-x86_64

EXPOSE 8000

ENTRYPOINT ["vllm", "serve"]

CMD ["Qwen/Qwen2.5-1.5B-Instruct", "--host", "0.0.0.0", "--port", "8000", "--served-model-name", "react-agent-model", "--max-model-len", "2048", "--max-num-seqs", "1", "--kv-cache-memory-bytes", "536870912", "--enable-auto-tool-choice", "--tool-call-parser", "hermes"]