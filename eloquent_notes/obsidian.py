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
                    try:
                        frontmatter = yaml.safe_load(frontmatter_str) or {}
                        existing_tags = frontmatter.get("tags", [])
                        if isinstance(existing_tags, str):
                            existing_tags = [existing_tags]
                        elif not isinstance(existing_tags, list):
                            existing_tags = []

                        # merge tags
                        for tag in tags:
                            if tag not in existing_tags:
                                existing_tags.append(tag)

                        frontmatter["tags"] = existing_tags

                        class CustomDumper(yaml.SafeDumper):
                            def ignore_aliases(self, data):
                                return True

                        new_frontmatter_str = yaml.dump(frontmatter, Dumper=CustomDumper, default_flow_style=False, sort_keys=False)

                        new_content = "---\n" + new_frontmatter_str + "---\n" + existing_content[end_frontmatter+3:].lstrip()

                    except yaml.YAMLError:
                        pass # if it fails to parse, just append to the end

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
