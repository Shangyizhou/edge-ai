"""Restore canonical tokenizer bytes for a pinned converter."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from .benchmark import file_hash, write_json


def stage_tokenizer(source, original, staging):
    """Keep tensors immutable and prove tokenizer semantics."""
    from transformers import AutoTokenizer

    source, original, staging = map(Path, (source, original, staging))
    staging.mkdir(parents=True, exist_ok=False)
    for path in source.iterdir():
        if path.is_file():
            if path.suffix == ".safetensors":
                (staging / path.name).symlink_to(path.resolve())
            else:
                shutil.copy2(path, staging / path.name)
    names = (
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
        "special_tokens_map.json",
        "vocab.json",
        "merges.txt",
        "tokenizer.model",
    )
    restored = []
    # Restore tokenizer files only in this new staging directory. The
    # original merged artifact and its recorded hashes remain untouched.
    for name in names:
        target = staging / name
        if target.exists():
            target.unlink()
        if (original / name).exists():
            shutil.copy2(original / name, target)
            restored.append({"name": name, "sha256": file_hash(target)})
    base = AutoTokenizer.from_pretrained(original, local_files_only=True)
    saved = AutoTokenizer.from_pretrained(source, local_files_only=True)
    messages = [{"role": "user", "content": "小沫，请播放“晴天”，音量35。"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "volume_set",
                "parameters": {
                    "type": "object",
                    "properties": {"level": {"type": "number"}},
                },
            },
        }
    ]
    options = dict(
        tools=tools,
        tokenize=True,
        return_dict=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    before = base.apply_chat_template(messages, **options)
    after = saved.apply_chat_template(messages, **options)
    if before != after or base.get_vocab() != saved.get_vocab():
        raise ValueError(
            "merged tokenizer differs from original vocabulary/template"
        )
    proof = {
        "source": str(source),
        "canonical_tokenizer": str(original),
        "reason": "TF5 save extra_special_tokens list is incompatible with "
        "the pinned TF4 converter; restore original tokenizer bytes",
        "restored_files": restored,
        "vocabulary_equal": True,
        "nonthinking_tool_prompt_tokens_equal": True,
        "prompt_tokens": len(before),
        "token_ids": before,
        "tensor_storage": "symlinks to unchanged merged safetensors",
    }
    write_json(staging / "tokenizer-fidelity.json", proof)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--tokenizer-source", required=True, type=Path)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--converter-python", required=True)
    parser.add_argument("--converter", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    proof = stage_tokenizer(args.source, args.tokenizer_source, args.staging)
    print(json.dumps(proof, ensure_ascii=False), flush=True)
    completed = subprocess.run(
        [
            args.converter_python,
            str(args.converter),
            str(args.staging),
            "--outfile",
            str(args.output),
            "--outtype",
            "f16",
        ],
        check=False,
    )
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
