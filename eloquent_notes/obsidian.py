import os
import yaml
from datetime import datetime

def save_note(vault_path, folder, daily_notes, text, tags, template_standalone, template_daily_new, template_daily_append):
    expanded_vault = os.path.expanduser(vault_path)
    target_dir = os.path.join(expanded_vault, folder)
    os.makedirs(target_dir, exist_ok=True)
    
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    tags_formatted = ""
    if tags:
        tags_formatted = "\n".join([f"  - {tag}" for tag in tags])
    
    if daily_notes:
        note_path = os.path.join(target_dir, f"{date_str}.md")
        if not os.path.exists(note_path):
            content = template_daily_new.format(date=date_str, time=time_str, text=text, tags=tags_formatted)
            mode = "w"
        else:
            with open(note_path, "r", encoding="utf-8") as f:
                existing_content = f.read()

            new_content = existing_content
            if existing_content.startswith("---"):
                end_frontmatter = existing_content.find("---", 3)
                if end_frontmatter != -1:
                    frontmatter_str = existing_content[3:end_frontmatter]
                    frontmatter = yaml.safe_load(frontmatter_str) or {}

                    if "tags" not in frontmatter or not isinstance(frontmatter["tags"], list):
                        frontmatter["tags"] = []

                    for tag in tags:
                        if tag not in frontmatter["tags"]:
                            frontmatter["tags"].append(tag)

                    yaml.SafeDumper.ignore_aliases = lambda self, data: True
                    new_frontmatter_str = yaml.safe_dump(frontmatter, default_flow_style=False, sort_keys=False)

                    # Splice it back perfectly without stripping the entire right side whitespace/newlines
                    # `end_frontmatter + 3` gives us the exact position after the `---`
                    remainder = existing_content[end_frontmatter+3:]
                    # If it starts with a single newline, eat it because we provide one with `\n` below
                    if remainder.startswith('\n'):
                        remainder = remainder[1:]

                    new_content = f"---\n{new_frontmatter_str}---\n{remainder}"

            content = template_daily_append.format(date=date_str, time=time_str, text=text)

            with open(note_path, "w", encoding="utf-8") as f:
                f.write(new_content)
                f.write("\n" + content)
            return note_path
    else:
        timestamp = now.strftime("%Y-%m-%d-%H%M%S")
        note_path = os.path.join(target_dir, f"Dictation-{timestamp}.md")
        content = template_standalone.format(date=date_str, time=time_str, text=text, tags=tags_formatted)
        mode = "w"
        
    with open(note_path, mode, encoding="utf-8") as f:
        f.write(content)
    return note_path
