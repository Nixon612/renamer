import argparse
import datetime
import fnmatch
import json
import os
import re
import sys

parser = argparse.ArgumentParser(description="Bulk file renamer")
parser.add_argument("target", help="Folder path to rename files in, or 'undo'")

parser.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"), help="Replace OLD with NEW in filename stem")
parser.add_argument("--regex", nargs=2, metavar=("PATTERN", "REPL"), help="Regex search and replace in filename stem")
parser.add_argument("--prefix", default="", metavar="TEXT", help="Add TEXT to the start of filename stem")
parser.add_argument("--suffix", default="", metavar="TEXT", help="Add TEXT to the end of filename stem")
parser.add_argument("--case", choices=["lower", "upper", "title"], default="", help="Change stem case")
parser.add_argument("--number", default="", metavar="TEMPLATE", help="Sequential numbering using {n} and {name}")
parser.add_argument("--number-start", type=int, default=1, metavar="N", help="Starting number for {n} (default: 1)")
parser.add_argument("--number-pad", type=int, default=3, metavar="N", help="Zero-pad width for {n} (default: 3)")
parser.add_argument("--new-ext", default="", metavar="EXT", help="Change file extension (e.g. md or .md)")
parser.add_argument("--no-clean", action="store_true", help="Skip automatic cleanup of illegal characters")

parser.add_argument("--in-ext", default="", metavar="LIST", help="Comma-separated extensions to include (e.g. txt,jpg)")
parser.add_argument("--match", default="", metavar="GLOB", help="Only rename files matching wildcard (e.g. '*file*')")
parser.add_argument("--recursive", action="store_true", help="Include files inside subfolders")
parser.add_argument("--include-hidden", action="store_true", help="Include dotfiles starting with '.'")
parser.add_argument("--sort", choices=["name", "mtime", "ctime", "size"], default="name", help="Order files by")

parser.add_argument("--apply", action="store_true", help="Perform renames on disk (default is preview only)")
parser.add_argument("--force", action="store_true", help="Allow overwriting existing files not in the batch")

args = parser.parse_args()

undo_dir = os.path.join(os.path.expanduser("~"), ".renamer")

if args.target == "undo":
    if not os.path.isdir(undo_dir):
        print("Error: no undo logs found (directory ~/.renamer does not exist).")
        sys.exit(1)

    log_files = []
    for item in os.listdir(undo_dir):
        if item.startswith("undo-") and item.endswith(".json"):
            log_files.append(item)

    if len(log_files) == 0:
        print("Error: no undo logs found in " + undo_dir)
        sys.exit(1)

    log_files.sort()
    latest_log_name = log_files[-1]
    latest_log_path = os.path.join(undo_dir, latest_log_name)

    log_file = open(latest_log_path, "r", encoding="utf-8")
    records = json.load(log_file)
    log_file.close()

    records.reverse()

    temp_undo = []
    for i in range(len(records)):
        pair = records[i]
        original_path = pair[0]
        current_path = pair[1]

        if not os.path.exists(current_path):
            print("Error: cannot undo because file is missing: " + current_path)
            sys.exit(1)

        parent_dir = os.path.dirname(current_path)
        temp_name = ".renamer_undo_tmp_" + str(i)
        temp_path = os.path.join(parent_dir, temp_name)

        os.replace(current_path, temp_path)
        temp_undo.append((current_path, temp_path, original_path))

    for current_path, temp_path, original_path in temp_undo:
        os.replace(temp_path, original_path)
        print("Restored: " + current_path + " -> " + original_path)

    os.remove(latest_log_path)
    print("Undo complete (removed log: " + latest_log_name + ")")
    sys.exit(0)

folder = args.target

if not os.path.isdir(folder):
    print("Error: not a folder: " + folder)
    print("Note: folder must be the first argument (or use 'py renamer.py undo').")
    sys.exit(1)

in_exts = []
if args.in_ext != "":
    for item in args.in_ext.split(","):
        item = item.lower()
        if not item.startswith("."):
            item = "." + item
        in_exts.append(item)

new_ext = args.new_ext
if new_ext != "" and not new_ext.startswith("."):
    new_ext = "." + new_ext

file_paths = []
if args.recursive:
    for current_dir, dirs, files in os.walk(folder):
        for name in files:
            file_paths.append(os.path.join(current_dir, name))
else:
    for item in os.listdir(folder):
        full_item_path = os.path.join(folder, item)
        if os.path.isfile(full_item_path):
            file_paths.append(full_item_path)

if args.sort == "name":
    file_paths.sort(key=lambda p: os.path.basename(p).lower())
elif args.sort == "mtime":
    file_paths.sort(key=lambda p: os.path.getmtime(p))
elif args.sort == "ctime":
    file_paths.sort(key=lambda p: os.path.getctime(p))
elif args.sort == "size":
    file_paths.sort(key=lambda p: os.path.getsize(p))

plan = []
counter = args.number_start

for full_path in file_paths:
    parent_dir = os.path.dirname(full_path)
    entry = os.path.basename(full_path)

    if not args.include_hidden and entry.startswith("."):
        continue

    if args.match != "":
        if not fnmatch.fnmatch(entry, args.match):
            continue

    stem, ext = os.path.splitext(entry)

    if len(in_exts) > 0:
        if ext.lower() not in in_exts:
            continue

    if args.replace is not None:
        stem = stem.replace(args.replace[0], args.replace[1])

    if args.regex is not None:
        stem = re.sub(args.regex[0], args.regex[1], stem)

    stem = args.prefix + stem + args.suffix

    if args.case == "lower":
        stem = stem.lower()
    elif args.case == "upper":
        stem = stem.upper()
    elif args.case == "title":
        stem = stem.title()

    if args.number != "":
        num_str = str(counter).zfill(args.number_pad)
        stem = args.number.replace("{n}", num_str).replace("{name}", stem)
        counter = counter + 1

    if not args.no_clean:
        illegal_chars = '<>:"/\\|?*'
        for ch in illegal_chars:
            stem = stem.replace(ch, "_")

    if new_ext != "":
        ext = new_ext

    new_name = stem + ext

    if new_name == entry:
        continue

    new_path = os.path.join(parent_dir, new_name)
    plan.append((full_path, new_path))

source_paths = []
for old_path, new_path in plan:
    source_paths.append(old_path.lower())

seen_targets = []
for old_path, new_path in plan:
    target_key = new_path.lower()

    if target_key in seen_targets:
        print("Error: collision detected — multiple files would be renamed to: " + new_path)
        sys.exit(1)
    seen_targets.append(target_key)

    if not args.force:
        if os.path.exists(new_path) and target_key not in source_paths:
            print("Error: target file already exists: " + new_path + " (use --force to overwrite)")
            sys.exit(1)

if not args.apply:
    for old_path, new_path in plan:
        print("Would rename: " + old_path + " -> " + new_path)
else:
    if len(plan) > 0:
        if not os.path.exists(undo_dir):
            os.makedirs(undo_dir)

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        log_name = "undo-" + timestamp + ".json"
        log_path = os.path.join(undo_dir, log_name)

        undo_records = []
        for old_path, new_path in plan:
            undo_records.append([os.path.abspath(old_path), os.path.abspath(new_path)])

        log_file = open(log_path, "w", encoding="utf-8")
        json.dump(undo_records, log_file, indent=2)
        log_file.close()
        print("Saved undo log: " + log_path)

    temp_plan = []
    for i in range(len(plan)):
        old_path, new_path = plan[i]
        parent_dir = os.path.dirname(old_path)
        temp_name = ".renamer_tmp_" + str(i)
        temp_path = os.path.join(parent_dir, temp_name)

        os.replace(old_path, temp_path)
        temp_plan.append((old_path, temp_path, new_path))

    for old_path, temp_path, new_path in temp_plan:
        os.replace(temp_path, new_path)
        print("Renamed: " + old_path + " -> " + new_path)