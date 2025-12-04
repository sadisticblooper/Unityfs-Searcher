import os
import time
import mmap
from multiprocessing import Pool, cpu_count
import sys
import threading
import re
import csv
import io
import urllib.request
import urllib.error
import urllib.parse
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.text import Text
from rich import box

# --- Configuration ---
BUNDLE_FOLDER = "/storage/emulated/0/Bundles"
OUTPUT_FILE = "/storage/emulated/0/bundle_search_results.txt"

SET_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS93_FlKEXvd0Ng--g6SnnRe2hKuO3dVg343ugrEfLmczkKuuQOVwM5gqjk7PiniVfo03vLFuGkCMq6/pub?gid=241641798&single=true&output=csv"
MISC_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS93_FlKEXvd0Ng--g6SnnRe2hKuO3dVg343ugrEfLmczkKuuQOVwM5gqjk7PiniVfo03vLFuGkCMq6/pub?gid=1855152004&single=true&output=csv"

MAX_MATCHES_PER_FILE_DEFAULT = 3
MAX_MATCHES_PER_FILE_SET = 1
NUM_PROCESSES = cpu_count()

DELIMITERS_BYTES = [b',', b'+', b'*']
FILE_SEPARATOR = "\n"


file_paths = []
total_files = 0
hardcoded_sets = []
misc_items = []
keyword_to_label = {}


preload_files_done = threading.Event()
preload_sets_done = threading.Event()
preload_misc_done = threading.Event()

console = Console()

class BundleSearcherTUI:
    def __init__(self):
        self.results = []
        
    def clear_screen(self):
        console.clear()
        
    def print_header(self):
        self.clear_screen()
        console.print("🔍 UNITYFS BUNDLE SEARCHER 3.3", style="bold green", justify="center")
        console.print("by Nexora", style="purple", justify="center")
        console.print()

    def ensure_resource_ready(self, event, description):
        
        if event.is_set():
            return True
            
        console.print(f"[yellow]Wait: {description}[/]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description, total=None)
            event.wait()
        return True

    def show_main_menu(self):
        while True:
            self.print_header()
            
            console.print("SELECT AN OPTION:")
            console.print("1. 🔍 Search by word")
            console.print("2. 🎯 Search full set") 
            console.print("3. 📦 Search for Miscellaneous Asset")
            console.print("4. 🚪 Exit")
            console.print()
            
            choice = Prompt.ask("Enter your choice", choices=["1", "2", "3", "4"], default="1")
            
            if choice == '1':
                
                self.word_search()
            
            elif choice == '2':
                
                self.ensure_resource_ready(preload_sets_done, "Downloading Set Data...")
                self.set_search()
            
            elif choice == '3':
                
                self.ensure_resource_ready(preload_misc_done, "Downloading Misc Data...")
                self.misc_search()
            
            elif choice == '4':
                console.print("Goodbye! 👋")
                break
                
            console.print()
            if not Confirm.ask("Continue with another search?"):
                console.print("Goodbye! 👋")
                break
                
    def word_search(self):
        self.clear_screen()
        console.print("🔍 WORD SEARCH")
        console.print()
        
        
        keywords = Prompt.ask("Enter keyword to search(")
        
        
        self.ensure_resource_ready(preload_files_done, "Finishing file scan...")
        
        if not file_paths:
            console.print("[red]❌ No bundle files found in storage.[/]")
            return

        if not keywords:
            console.print("No keywords provided")
            return
            
        search_keywords = [kw.strip() for kw in keywords.split(',') if kw.strip()]
        console.print(f"Searching for: {', '.join(search_keywords)}")
        console.print()
        
        self.perform_search_with_progress(search_keywords, "word")
        
    def set_search(self):
        self.clear_screen()
        console.print("🎯 SET SEARCH")
        console.print()
        
        if not hardcoded_sets:
            console.print("[red]❌ No sets loaded. Check network or source URL.[/]")
            return
            
        # Show available sets
        table = Table(title="Available Sets", box=box.ROUNDED)
        table.add_column("No.", style="cyan", width=5)
        table.add_column("Set Name", style="green")
        table.add_column("Items", style="white")
        
        for i, (name, keywords) in enumerate(hardcoded_sets, 1):
            items = [f"{kw.strip()} ({keyword_to_label.get(kw.strip(), 'Unknown')})" 
                    for kw in keywords.split(',')]
            table.add_row(str(i), name, ", ".join(items[:3]) + ("..." if len(items) > 3 else ""))
            
        console.print(table)
        console.print()
        
        try:
            set_choice = IntPrompt.ask("Enter the number of the set", default=1, show_default=True)
            if 1 <= set_choice <= len(hardcoded_sets):
                name, keywords_str = hardcoded_sets[set_choice - 1]
                search_keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
                
                
                self.ensure_resource_ready(preload_files_done, "Finishing file scan...")
                
                self.clear_screen()
                console.print("🎯 SET SEARCH")
                console.print(f"Selected set: {name}")
                console.print(f"Searching for: {', '.join(search_keywords)}")
                console.print()
                
                self.perform_search_with_progress(search_keywords, "set")
            else:
                console.print("Invalid set number")
        except ValueError:
            console.print("Invalid input")
            
    def misc_search(self):
        self.clear_screen()
        console.print("📦 MISCELLANEOUS ASSET SEARCH")
        console.print()
        
        if not misc_items:
            console.print("[red]❌ No miscellaneous assets loaded. Check network.[/]")
            return
            
        
        table = Table(title="Available Miscellaneous Assets", box=box.ROUNDED)
        table.add_column("No.", style="cyan", width=5)
        table.add_column("Asset Name", style="green")
        table.add_column("Identifier", style="white")
        
        for i, (name, identifier) in enumerate(misc_items, 1):
            table.add_row(str(i), name, identifier)
            
        console.print(table)
        console.print()
        
        try:
            item_choice = IntPrompt.ask("Enter the number of the asset to find", default=1, show_default=True)
            if 1 <= item_choice <= len(misc_items):
                name, identifier = misc_items[item_choice - 1]
                
                
                self.ensure_resource_ready(preload_files_done, "Finishing file scan...")
                
                self.clear_screen()
                console.print("📦 MISCELLANEOUS ASSET SEARCH")
                console.print(f"Selected asset: {name}")
                console.print(f"Searching for identifier: {identifier}")
                console.print()
                
                self.perform_search_with_progress([identifier], "word")
            else:
                console.print("Invalid asset number")
        except ValueError:
            console.print("Invalid input")
            
    def perform_search_with_progress(self, search_keywords, search_type):
        if not file_paths:
            console.print("No bundle files found")
            return
            
        if not search_keywords:
            console.print("No keywords provided")
            return
            
        if search_type == "word":
            results = self.perform_word_search(search_keywords)
            self.display_word_results(results, search_keywords)
        else:
            results = self.perform_set_search(search_keywords)
            self.display_set_results(results, search_keywords)
            
    def perform_word_search(self, search_keywords):
        keywords_lower_bytes = [kw.encode("utf-8").lower() for kw in search_keywords]
        
        console.print(f"Starting word search across {total_files} files with {NUM_PROCESSES} cores...")
        
        task_args = [(fp, keywords_lower_bytes, 'word') for fp in file_paths]
        results_list = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Searching files...", total=len(task_args))
            
            with Pool(processes=NUM_PROCESSES) as pool:
                for filename, matches in pool.imap_unordered(process_file_for_search, task_args, chunksize=10):
                    if matches:
                        results_list.append((filename, matches))
                    progress.update(task, advance=1, description=f"Found {len(results_list)} matches")
        
        results_list.sort()
        return results_list
        
    def perform_set_search(self, search_keywords):
        keywords_lower = [kw.encode("utf-8").lower() for kw in search_keywords]
        
        console.print(f"Starting set search across {total_files} files with {NUM_PROCESSES} cores...")
        
        task_args = [(fp, keywords_lower, 'set') for fp in file_paths]
        all_results = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Searching files...", total=len(task_args))
            
            with Pool(processes=NUM_PROCESSES) as pool:
                for filename, found in pool.imap_unordered(process_file_for_search, task_args, chunksize=10):
                    if found:
                        all_results.append((filename, found))
                    progress.update(task, advance=1, description=f"Found {len(all_results)} files with matches")
        
        return all_results
        
    def display_word_results(self, results, search_keywords):
        console.print()
        console.print("🎉 Word Search Complete!")
        console.print(f"Search terms: {', '.join(search_keywords)}")
        console.print()
        
        if not results:
            console.print("No results found.")
            return
            
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as out_file:
            out_file.write("Found String | Source File\n" + "=" * 60 + "\n\n")
            for filename, matches in results:
                for m in matches:
                    out_file.write(f"{m} | {filename}\n")
                out_file.write(FILE_SEPARATOR)
        
        
        total_matches = sum(len(m) for _, m in results)
        console.print("📊 Summary:")
        console.print(f"   Files with matches: {len(results)}")
        console.print(f"   Total matches: {total_matches}")
        console.print(f"   Results saved to: {OUTPUT_FILE}")
        console.print()
        
        
        console.print("First few results:")
        table = Table(box=box.SIMPLE)
        table.add_column("Match", style="green")
        table.add_column("File", style="cyan")
        
        count = 0
        for filename, matches in results:
            for match in matches[:2]:  
                if count < 10:  # Show max 10 results in preview
                    table.add_row(match[:80] + ("..." if len(match) > 80 else ""), filename)
                    count += 1
            if count >= 10:
                break
                
        console.print(table)
        if total_matches > 10:
            console.print(f"... and {total_matches - 10} more results in output file")
            
    def display_set_results(self, results, search_keywords):
        console.print()
        console.print("🎉 Set Search Complete!")
        console.print()
        
        if not results:
            console.print("No results found.")
            return
            
        
        console.print("Results:")
        table = Table(box=box.ROUNDED)
        table.add_column("File", style="cyan")
        table.add_column("Found Items", style="green")
        table.add_column("Status", style="yellow")
        
        full_sets = 0
        partial_matches = 0
        
        for filename, found_kws in sorted(results):
            if len(found_kws) == len(search_keywords):
                status = "✅ Full Set"
                full_sets += 1
                items_text = "All items"
            else:
                status = "⚠️ Partial"
                partial_matches += 1
                items = []
                for kw in found_kws:
                    label = keyword_to_label.get(kw, kw)
                    items.append(f"{kw} ({label})")
                items_text = ", ".join(items)
                
            table.add_row(filename, items_text, status)
            
        console.print(table)
        console.print()
        console.print("📊 Summary:")
        console.print(f"   Full sets found: {full_sets}")
        console.print(f"   Partial matches: {partial_matches}")
        console.print(f"   Total files with matches: {len(results)}")

def load_hardcoded_sets_from_url():
    global hardcoded_sets, keyword_to_label
    hardcoded_sets, keyword_to_label = [], {}

    try:
        with urllib.request.urlopen(SET_SHEET_URL) as response:
            csv_data = response.read().decode('utf-8')

        reader = csv.reader(io.StringIO(csv_data))
        headers = next(reader, None)
        if not headers:
            return

        header_indices = {h.strip().lower(): i for i, h in enumerate(headers)}
        set_name_col = header_indices.get("set name")
        if set_name_col is None:
            return
            
        item_columns = {"helm": "helmet", "armour": "armour", "wpn": "weapon", "rng": "ranged weapon", "animation": "animation","boss head": "boss head"}

        for row in reader:
            if not row or len(row) <= set_name_col or not row[set_name_col].strip():
                continue
            set_name = row[set_name_col].strip()
            keywords = []
            for header, label in item_columns.items():
                col_idx = header_indices.get(header)
                if col_idx is not None and len(row) > col_idx and row[col_idx].strip():
                    item_keywords = [kw.strip() for kw in row[col_idx].split(',') if kw.strip()]
                    for kw in item_keywords:
                        keyword_to_label[kw] = label
                    keywords.extend(item_keywords)
            if keywords:
                hardcoded_sets.append((set_name, ",".join(keywords)))
    except Exception as e:
        pass
    finally:
        preload_sets_done.set()

def load_misc_items_from_url():
    global misc_items
    misc_items = []
    try:
        with urllib.request.urlopen(MISC_SHEET_URL) as response:
            csv_data = response.read().decode('utf-8')

        reader = csv.reader(io.StringIO(csv_data))
        headers = next(reader, None) 

        for row in reader:
            if len(row) >= 2 and row[0].strip() and row[1].strip():
                asset_name = row[0].strip()
                asset_identifier = row[1].strip()
                misc_items.append((asset_name, asset_identifier))
    except Exception as e:
        pass
    finally:
        preload_misc_done.set()

def clean_snippet(text: str) -> str:
    text = re.sub(r"[\x00-\x1F\x7F]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def process_file_for_search(args):
    file_path, keywords_lower, search_mode = args
    results = []
    try:
        with open(file_path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            if search_mode == 'word':
                primary_kw, *additional_kws = keywords_lower
                pos = 0
                while len(results) < MAX_MATCHES_PER_FILE_DEFAULT:
                    pos = mm.find(primary_kw, pos)
                    if pos == -1: break
                    
                    start = mm.rfind(b"\x00", 0, pos) + 1
                    end = mm.find(b"\x00", pos)
                    chunk = mm[start:end if end != -1 else mm.size()]
                    
                    is_valid = not additional_kws or all(kw in chunk.lower() for kw in additional_kws)
                    
                    if is_valid:
                        first_delim = min((chunk.find(d) for d in DELIMITERS_BYTES if d in chunk), default=len(chunk))
                        snippet = chunk[:first_delim].decode("utf-8", errors="ignore")
                        if snippet: results.append(clean_snippet(snippet))
                    pos += len(primary_kw)
            elif search_mode == 'set':
                for kw in keywords_lower:
                    if mm.find(kw) != -1:
                        results.append(kw.decode("utf-8"))
                        if MAX_MATCHES_PER_FILE_SET == 1: break
    except Exception:
        pass
    return os.path.basename(file_path), results

def preload_file_paths():
    global file_paths, total_files
    if not os.path.exists(BUNDLE_FOLDER):
        preload_files_done.set()
        return
    all_files = sorted([f for f in os.listdir(BUNDLE_FOLDER) if os.path.isfile(os.path.join(BUNDLE_FOLDER, f)) and "download" not in f.lower()])
    file_paths = [os.path.join(BUNDLE_FOLDER, f) for f in all_files]
    total_files = len(file_paths)
    preload_files_done.set()

def main():
    
    threading.Thread(target=preload_file_paths, daemon=True).start()
    threading.Thread(target=load_hardcoded_sets_from_url, daemon=True).start()
    threading.Thread(target=load_misc_items_from_url, daemon=True).start()
    
    
    app = BundleSearcherTUI()
    app.show_main_menu()

if __name__ == "__main__":
    main()
