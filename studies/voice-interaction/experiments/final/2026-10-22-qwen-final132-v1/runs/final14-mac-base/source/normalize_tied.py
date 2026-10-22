"""Normalize a verified duplicate Qwen tied head."""

import argparse
import json
import shutil
from pathlib import Path

from .benchmark import file_hash, write_json


def normalize(source, output):
    import mlx.core as mx

    source, output = Path(source), Path(output)
    config = json.loads((source / "config.json").read_text())
    if config.get("tie_word_embeddings") is not True:
        raise ValueError("explicit tied embedding config required")
    if config.get("model_type") != "qwen3":
        raise ValueError("only the verified Qwen3 serialization is supported")
    files = list(source.glob("*.safetensors"))
    if len(files) != 1:
        raise ValueError("expected one nonsharded source safetensor")
    weights = mx.load(str(files[0]))
    embedding, head = "model.embed_tokens.weight", "lm_head.weight"
    if weights[embedding].dtype != weights[head].dtype:
        raise ValueError("tied tensors have different dtypes")
    if not mx.array_equal(weights[embedding], weights[head]).item():
        raise ValueError("tied tensors are not bit-value identical")
    original_count = sum(w.size for w in weights.values())
    removed = weights.pop(head)
    output.mkdir(parents=True, exist_ok=False)
    for path in source.iterdir():
        if path.is_file() and path.suffix != ".safetensors":
            shutil.copy2(path, output / path.name)
    target = output / "model.safetensors"
    mx.save_safetensors(str(target), weights)
    emitted = mx.load(str(target))
    if set(emitted) != set(weights) or not all(
        emitted[k].dtype == weights[k].dtype
        and mx.array_equal(emitted[k], weights[k]).item()
        for k in weights
    ):
        raise ValueError("output tensor identity verification failed")
    proof = {
        "source": str(source),
        "source_sha256": file_hash(files[0]),
        "output_sha256": file_hash(target),
        "config_tie_word_embeddings": True,
        "duplicate_head_equal_to_embedding": True,
        "all_retained_tensors_value_and_dtype_equal": True,
        "removed_tensor": head,
        "removed_parameters": removed.size,
        "source_stored_parameters": original_count,
        "output_unique_parameters": sum(w.size for w in emitted.values()),
        "operation": "serialization normalization; no training or tensor math",
    }
    write_json(output / "tied-normalization-proof.json", proof)
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(normalize(args.source, args.output), indent=2))
