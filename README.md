# Medical Notes

Quartz site built from the medical notes in my Obsidian vault.
Live at https://daksh-4.github.io/medical-notes

## Updating the notes
    python3 sync.py "/path/to/Daksh"   # rebuilds content/ from the vault (vault is never modified)
    git add -A && git commit -m "Update notes" && git push

Rules (see sync.py): a note is published if it links to a file in `3-Tags`
(frontmatter `tags:` or a `[[Tag]]` link), unless it contains `#incorrect` or its
title is in `exclude.txt`. Only attachments embedded by published notes are copied.
Links to unpublished notes become plain text.

## Preview locally
    npm ci && npx quartz plugin install && npx quartz build --serve   # http://localhost:8080
