#!/usr/bin/env python3
"""
scripts/benchmark_models.py

Standalone model benchmarking script.
"""
from __future__ import annotations
import sys

def main():
    print("Starting benchmarks...")
    try:
        from friday.models.ollama_backend import OllamaProvider
        from friday.models.benchmark import ModelBenchmark
        
        provider = OllamaProvider(model="qwen3:8b")
        bench = ModelBenchmark(provider)
        res = bench.run_full_benchmark("qwen3:8b", "reasoning")
        print(f"Results: {res}")
    except ImportError:
        print("friday module missing.")

if __name__ == "__main__":
    main()
