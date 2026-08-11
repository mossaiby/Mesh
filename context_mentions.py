import os
import re
from typing import Tuple, List
from theme import console


def process_prompt_context_mentions(prompt: str, root_dir: str = ".") -> Tuple[str, List[str]]:
    """
    Parses user prompt for `@filepath` mentions. If filepath exists on disk,
    reads its contents and appends formatted context blocks into the prompt payload.
    Returns (updated_prompt, list_of_attached_files).
    """
    # Regex matching @filepath patterns (e.g., @src/engine.py, @README.md)
    mention_pattern = r'@(["\']?[\w\.\-/\\]+["\']?)'
    matches = re.findall(mention_pattern, prompt)

    if not matches:
        return prompt, []

    attached_files = []
    attachments_markdown = []

    for raw_match in matches:
        clean_path = raw_match.strip('"').strip("'")
        full_path = os.path.join(root_dir, clean_path)

        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                ext = os.path.splitext(clean_path)[1].lstrip(".") or "text"
                attachments_markdown.append(
                    f"[Attached Context from @{clean_path}]:\n```{ext}\n{content}\n```"
                )
                attached_files.append(clean_path)
            except Exception:
                pass

    if attached_files:
        for f_name in attached_files:
            console.print(f"[success]📎 Attached file context for @{f_name}[/success]")

        context_block = "\n\n".join(attachments_markdown)
        updated_prompt = f"{prompt}\n\n{context_block}"
        return updated_prompt, attached_files

    return prompt, []