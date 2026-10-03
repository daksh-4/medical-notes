#!/usr/bin/env python3
"""Build content/ for the medical-notes site from an Obsidian vault.

Usage:  python3 sync.py "/path/to/Daksh"        (never modifies the vault)

A note is published if it links to a file in 3-Tags (frontmatter `tags:` list
or a [[Tag]] wikilink), unless it contains #incorrect or is listed in
exclude.txt (one note title per line).
"""
import os, re, sys, shutil, json, collections

vault = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VAULT", ""))
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "content")
NOTES, TAGS, ATT = (os.path.join(vault, d) for d in ("6-Main-Notes", "3-Tags", "7-Attachments"))
for d in (NOTES, TAGS, ATT):
    if not os.path.isdir(d):
        sys.exit(f"Not found: {d}")

exclude = set()
ex = os.path.join(here, "exclude.txt")
if os.path.exists(ex):
    exclude = {l.strip() for l in open(ex, encoding="utf-8") if l.strip() and not l.startswith("#")}

tags = sorted(f[:-3] for f in os.listdir(TAGS) if f.endswith(".md"))
tagset = set(tags)

def read(p):
    return open(p, encoding="utf-8").read()

def split_fm(t):
    m = re.match(r"---\n(.*?)\n---\n?", t, re.S)
    return (m.group(1), t[m.end():]) if m else ("", t)

def note_links(t):
    fm, body = split_fm(t)
    links = {x.split("#")[0].strip() for x in re.findall(r"(?<!!)\[\[([^\]|]+)", body)}
    links |= {x.split("#")[0].strip() for x in re.findall(r"!\[\[([^\]|]+)", body)}
    links |= {x.strip().strip("\"'") for x in re.findall(r"^\s+-\s*(.+)$", fm, re.M)}
    return links

selected, dropped = {}, collections.defaultdict(list)
for f in sorted(os.listdir(NOTES)):
    if not f.endswith(".md"):
        continue
    title = f[:-3]
    t = read(os.path.join(NOTES, f))
    if not (note_links(t) & tagset):
        continue
    if re.search(r"#incorrect\b", t, re.I):
        dropped["#incorrect"].append(title); continue
    if title in exclude:
        dropped["exclude.txt"].append(title); continue
    selected[title] = t

att_files = {f: os.path.join(ATT, f) for f in os.listdir(ATT) if os.path.isfile(os.path.join(ATT, f))}
published = set(selected) | tagset

if os.path.isdir(out):
    shutil.rmtree(out)
os.makedirs(os.path.join(out, "attachments"))

used_att = set()
unresolved = collections.Counter()

def fix(t):
    fm, body = split_fm(t)
    # drop the Obsidian-only "Status: #red/#orange/#yellow" revision flag so it doesn't become a tag
    body = re.sub(r"^Status:\s*#(red|orange|yellow|green)\s*$", "", body, flags=re.M | re.I)
    def emb(m):
        base = m.group(1).strip().split("#")[0]
        if base in att_files:
            used_att.add(base); return m.group(0)
        if base in published:
            return m.group(0)
        unresolved[base] += 1
        return ""
    body = re.sub(r"!\[\[([^\]|]+)(\|[^\]]*)?\]\]", emb, body)
    def link(m):
        tgt, alias = m.group(1).strip(), (m.group(2) or "")[1:]
        base = tgt.split("#")[0]
        if base in published or base in att_files:
            if base in att_files: used_att.add(base)
            return m.group(0)
        unresolved[base] += 1
        return alias or (base if "#" not in tgt else tgt.replace("#", " > "))
    body = re.sub(r"(?<!!)\[\[([^\]|]+)(\|[^\]]*)?\]\]", link, body)
    return (f"---\n{fm}\n---\n" if fm else "") + body

for title, t in selected.items():
    open(os.path.join(out, title + ".md"), "w", encoding="utf-8").write(fix(t))

counts = collections.Counter()
for title, t in selected.items():
    for l in note_links(t) & tagset:
        counts[l] += 1
for tg in tags:
    open(os.path.join(out, tg + ".md"), "w", encoding="utf-8").write(
        f"---\ntitle: {tg}\n---\n\nNotes linked to **{tg}** are listed under *Backlinks*.\n")

try:
    from PIL import Image
except ImportError:
    Image = None
MAXW = 1800  # shrink very wide screenshots; lossless otherwise
cache = os.path.join(here, ".img-cache")   # makes re-runs fast; safe to delete
os.makedirs(cache, exist_ok=True)
import time
from multiprocessing import Pool

def process(a):
    src = att_files[a]
    key = os.path.join(cache, f"{int(os.path.getmtime(src))}-{a}")
    if os.path.exists(key):
        return a, key
    done = False
    if Image and a.lower().endswith(".png"):
        try:
            im = Image.open(src); im.load()
            if im.width > MAXW:
                im = im.resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)
            im.save(key + ".tmp", format="PNG", compress_level=9)
            done = os.path.getsize(key + ".tmp") < os.path.getsize(src)
            if done:
                os.replace(key + ".tmp", key)
            else:
                os.remove(key + ".tmp")
        except Exception as e:
            print("copy as-is:", a, e)
    if not done:
        shutil.copy2(src, key)
    return a, key

t0 = time.time()
with Pool(max(2, (os.cpu_count() or 2))) as pool:
    for a, key in pool.imap_unordered(process, sorted(used_att)):
        shutil.copy2(key, os.path.join(out, "attachments", a))
print(f"images processed in {time.time()-t0:.0f}s")

rows = "\n".join(f"- [[{tg}]] — {counts[tg]} notes" for tg in tags if counts[tg])
open(os.path.join(out, "index.md"), "w", encoding="utf-8").write(
    "---\ntitle: Medical Notes\n---\n\nSearchable study notes. Use the search box or browse by specialty:\n\n"
    + rows + f"\n\n*{len(selected)} notes.*\n")

report = {"selected": sorted(selected), "dropped": dropped, "attachments": len(used_att),
          "unresolved_links": unresolved.most_common()}
json.dump(report, open(os.path.join(here, "sync-report.json"), "w"), indent=1)
size = sum(os.path.getsize(os.path.join(out, "attachments", a)) for a in used_att if os.path.exists(os.path.join(out, "attachments", a))) / 1e6
print(f"{len(selected)} notes, {len(used_att)} attachments ({size:.0f} MB)")
print({k: len(v) for k, v in dropped.items()}, "| unresolved link targets:", len(unresolved))
