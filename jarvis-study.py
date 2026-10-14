#!/usr/bin/env python3
"""Pull a bCourses class into ~/jarvis/study/<class>/ so Jarvis can read it.

Downloads: the course's files (lecture slides, readings, guides), the list of
assignments with due dates, and the syllabus. Nothing is changed on bCourses;
this only reads.

Run:   cd ~/jarvis && python3 jarvis-study.py
Token: ~/jarvis/canvas-token.txt (one line, from bCourses -> Account -> Settings)
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BCOURSES = "https://bcourses.berkeley.edu"
COURSE_MATCH = "UGBA 178"          # part of the course name to pick
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, "canvas-token.txt")
OUT = os.path.join(HERE, "study")


def token():
    try:
        with open(TOKEN_FILE) as f:
            t = f.read().strip()
    except OSError:
        sys.exit("No canvas-token.txt next to this script. Make it with: pbpaste > ~/jarvis/canvas-token.txt")
    if not t:
        sys.exit("canvas-token.txt is empty.")
    return t


TOKEN = token()


def api(path, **params):
    """GET one Canvas API path, following 'next' pages. Returns a list."""
    params.setdefault("per_page", 100)
    url = BCOURSES + "/api/v1" + path + "?" + urllib.parse.urlencode(params, doseq=True)
    out = []
    while url:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
            out.extend(data if isinstance(data, list) else [data])
            link = r.headers.get("Link", "")
            m = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = m.group(1) if m else None
    return out


def safe(name):
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip() or "file"


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return "already had"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    return "downloaded"


def main():
    courses = api("/courses", enrollment_state="active", include=["term"])
    course = next((c for c in courses if COURSE_MATCH.lower() in (c.get("name") or "").lower()
                   or COURSE_MATCH.lower() in (c.get("course_code") or "").lower()), None)
    if not course:
        print("Couldn't find a course matching %r. Your courses:" % COURSE_MATCH)
        for c in courses:
            print("  -", c.get("name"), "|", c.get("course_code"))
        sys.exit(1)
    cid = course["id"]
    folder = os.path.join(OUT, safe(COURSE_MATCH.replace(" ", "").lower()))
    os.makedirs(os.path.join(folder, "files"), exist_ok=True)
    print("Course:", course.get("name"), "(id %s)" % cid)
    print("Folder:", folder)

    # 1. assignments (the midterm lives here)
    assignments = api("/courses/%s/assignments" % cid, order_by="due_at")
    with open(os.path.join(folder, "assignments.json"), "w") as f:
        json.dump(assignments, f, indent=1)
    print("\nAssignments:")
    os.makedirs(os.path.join(folder, "assignments"), exist_ok=True)
    for a in assignments:
        print("  %-12s %s" % ((a.get("due_at") or "no due")[:10], a.get("name")))
        # files attached inside the assignment text (the midterm prompt lives here)
        for fid in set(re.findall(r"/files/(\d+)", a.get("description") or "")):
            try:
                fl = api("/files/%s" % fid)[0]
                name = safe(fl.get("display_name") or fl.get("filename") or fid)
                dest = os.path.join(folder, "assignments", name)
                print("      %-11s %s" % (download(fl["url"], dest), name))
            except Exception as e:
                print("      FAILED file %s: %s" % (fid, e))

    # 2. syllabus
    full = api("/courses/%s" % cid, include=["syllabus_body"])[0]
    if full.get("syllabus_body"):
        with open(os.path.join(folder, "syllabus.html"), "w") as f:
            f.write(full["syllabus_body"])
        print("\nSyllabus saved.")

    # 3. files: everything the Files tab and the Modules link to
    files = {}
    try:
        for fl in api("/courses/%s/files" % cid):
            files[fl["id"]] = fl
    except urllib.error.HTTPError as e:
        print("\n(Files tab not open to students: %s. Using modules only.)" % e.code)
    modules = []
    try:
        modules = api("/courses/%s/modules" % cid, include=["items"])
    except urllib.error.HTTPError as e:
        print("(Modules not readable: %s)" % e.code)
    plan = []
    for m in modules:
        for it in m.get("items") or []:
            if it.get("type") == "File" and it.get("content_id"):
                fid = it["content_id"]
                if fid not in files:
                    try:
                        files[fid] = api("/files/%s" % fid)[0]
                    except Exception:
                        continue
                files[fid]["_module"] = m.get("name")
                files[fid]["_position"] = (m.get("position", 0), it.get("position", 0))
        plan.append({"module": m.get("name"), "items": [(it.get("type"), it.get("title")) for it in m.get("items") or []]})
    with open(os.path.join(folder, "modules.json"), "w") as f:
        json.dump(plan, f, indent=1)

    print("\nFiles (%d):" % len(files))
    index = []
    for fl in sorted(files.values(), key=lambda x: (x.get("_position", (999, 999)), x.get("display_name", ""))):
        name = safe(fl.get("display_name") or fl.get("filename") or str(fl["id"]))
        dest = os.path.join(folder, "files", name)
        try:
            status = download(fl["url"], dest)
        except Exception as e:
            status = "FAILED: %s" % e
        index.append({"name": name, "module": fl.get("_module"), "size": fl.get("size"), "updated": fl.get("updated_at")})
        print("  %-11s %s   [%s]" % (status, name, fl.get("_module") or "Files"))
    with open(os.path.join(folder, "index.json"), "w") as f:
        json.dump(index, f, indent=1)
    print("\nDone. Everything is in", folder)


if __name__ == "__main__":
    main()
