"""
Timetable Generator (Python)
Generates multiple conflict-free timetables (alternatives) given user inputs.

How it works (high-level):
- You provide a configuration (either interactively or via a JSON file) that describes:
  number of timetables to generate, timetable names, list of classrooms (and capacities - optional),
  lecture_slot_length (minutes), subjects (with weekly sessions and duration in slots), faculty list,
  recess (after how many slots or at which slot), working_days, day start/end times.
- The solver builds slots for each day, inserts recess slots, then uses a backtracking + randomization
  approach to assign each required lecture session to a slot, a classroom, and a faculty member,
  ensuring:
    * No faculty teaches two sessions at the same time.
    * No classroom is double-booked.
    * If a subject requires consecutive slots (e.g. 120 minutes), the solver looks for adjacent free slots.
- Generates up to `num_timetables` different valid timetables (tries multiple random restarts to get distinct ones).

Usage:
- You can run this script and follow the interactive prompts, OR provide a JSON config file and run:
    python timetable_generator.py --config sample_config.json

Outputs:
- CSV files (one per timetable) saved in ./outputs/ (timetable_<name>.csv) and JSON versions.

Notes & limitations:
- This script is a practical starting point. Real college timetabling can require many custom constraints
  (teacher preferences, subject sequencing, room features, cross-listed subjects, etc.). Those can be
  added into the `constraints` section of the config and the `is_valid_assignment` function.

"""

import argparse
import json
import os
import random
import csv
import copy
from datetime import datetime, timedelta
from tabulate import tabulate 


# --------------------------- Data structures --------------------------------

class Slot:
    def __init__(self, day_index, slot_index, start_time_str):
        self.day_index = day_index  # 0..D-1
        self.slot_index = slot_index  # index within day excluding recess slots
        self.start_time_str = start_time_str

    def id(self):
        return f"D{self.day_index}_S{self.slot_index}"

    def __repr__(self):
        return self.id()


# A single lecture session requirement
class LectureReq:
    def __init__(self, timetable_name, subject_code, subject_name, faculty, slots_needed, preferred_room=None):
        self.timetable_name = timetable_name
        self.subject_code = subject_code
        self.subject_name = subject_name
        self.faculty = faculty
        self.slots_needed = slots_needed  # integer number of slots (each slot length = base slot len)
        self.preferred_room = preferred_room

    def uid(self):
        return f"{self.timetable_name}::{self.subject_code}::{self.faculty}::{random.random()}"

    def __repr__(self):
        return f"{self.subject_code}({self.faculty}, {self.slots_needed})"


# --------------------------- Helper functions -------------------------------

def build_day_slots(day_start, day_end, slot_length_minutes):
    """
    Returns list of (slot_index, start_time_str) for a single working day.
    Automatically inserts a recess (blocks one slot) near mid-day only if the
    working day duration is at least 4 hours. For shorter days, no recess.
    """
    fmt = "%H:%M"
    start = datetime.strptime(day_start, fmt)
    end = datetime.strptime(day_end, fmt)
    # Build base slots
    base = []
    idx = 0
    cur = start
    while cur + timedelta(minutes=slot_length_minutes) <= end:
        base.append((idx, cur.strftime(fmt)))
        idx += 1
        cur = cur + timedelta(minutes=slot_length_minutes)

    total_minutes = int((end - start).total_seconds() // 60)
    if total_minutes < 240 or len(base) == 0:
        return base

    # choose the slot closest to mid-time as recess
    mid = start + (end - start) / 2
    closest_j = None
    closest = None
    for j, (_, t) in enumerate(base):
        tdt = datetime.strptime(t, fmt).replace(year=mid.year, month=mid.month, day=mid.day)
        delta = abs((tdt - mid).total_seconds())
        if closest is None or delta < closest:
            closest = delta
            closest_j = j

    filtered = [(i, t) for k, (i, t) in enumerate(base) if k != closest_j]
    # reindex to keep slot_index contiguous within the day
    reindexed = [(k, t) for k, (_, t) in enumerate(filtered)]
    return reindexed


def shuffle_and_try_assign(reqs, slots, rooms, faculties):
    """
    Attempt to assign each LectureReq in reqs to available slots and rooms with backtracking.
    Returns assignment dict or None.
    assignment structure: {lecture_uid: (list_of_Slot_ids, room)}
    """
    # Pre-calc useful maps
    slot_ids = [s.id() for s in slots]

    # availability maps
    room_busy = {room: set() for room in rooms}
    faculty_busy = {f: set() for f in faculties}

    assignments = {}

    # Order requirements heuristically (longer sessions first)
    reqs_sorted = sorted(reqs, key=lambda r: -r.slots_needed)

    # helper to check if consecutive slots exist starting at some index
    slot_index_map = {slots[i].id(): i for i in range(len(slots))}

    def backtrack(i):
        if i >= len(reqs_sorted):
            return True
        req = reqs_sorted[i]
        # generate candidate start positions (randomized for diversity)
        indices = list(range(len(slots)))
        random.shuffle(indices)
        for start_idx in indices:
            end_idx = start_idx + req.slots_needed - 1
            if end_idx >= len(slots):
                continue
            candidate_slot_ids = [slots[j].id() for j in range(start_idx, end_idx + 1)]
            # Check faculty availability
            conflict_fac = any(sid in faculty_busy.get(req.faculty, set()) for sid in candidate_slot_ids)
            if conflict_fac:
                continue
            # Choose room: try preferred first
            room_list = rooms[:] if req.preferred_room is None else [req.preferred_room] + [r for r in rooms if r != req.preferred_room]
            room_found = None
            for room in room_list:
                if all((sid not in room_busy[room]) for sid in candidate_slot_ids):
                    room_found = room
                    break
            if room_found is None:
                continue
            # assign
            assignments[req.uid()] = (candidate_slot_ids, room_found, req)
            for sid in candidate_slot_ids:
                room_busy[room_found].add(sid)
                faculty_busy[req.faculty].add(sid)
            # recurse
            if backtrack(i + 1):
                return True
            # undo
            for sid in candidate_slot_ids:
                room_busy[room_found].remove(sid)
                faculty_busy[req.faculty].remove(sid)
            del assignments[req.uid()]
        return False

    ok = backtrack(0)
    return assignments if ok else None


# --------------------------- Main solver -----------------------------------

def generate_single_timetable(config, timetable_name, random_seed=None):
    random_seed = random_seed or random.randint(1, 10**9)
    random.seed(random_seed)

    # Build slots across days
    working_days = config['working_days']
    day_start = config['day_start']
    day_end = config['day_end']
    slot_len = config['lecture_slot_length_minutes']
    
    # Get day names if available, otherwise use default numbering
    day_names = config.get('selected_days', [f"Day {i+1}" for i in range(working_days)])
    
    all_slots = []
    for d in range(working_days):
        day_slots = build_day_slots(day_start, day_end, slot_len)
        # convert to Slot objects but include day offset in slot_index
        for si, start_time in day_slots:
            # if recess position should be skipped we could mark it later; here we keep linear list
            s = Slot(day_index=d, slot_index=si, start_time_str=start_time)
            all_slots.append(s)

    rooms = [r['name'].strip() for r in config['rooms']]
    faculties = [f['name'].strip() for f in config['faculties']]

    # Expand subject session requirements into LectureReq items
    reqs = []
    for subj in config['subjects']:
        subj_code = subj.get('code', subj['name'])
        subj_name = subj['name']
        faculty = subj['faculty'].strip()  # Trim whitespace
        sessions_per_week = subj.get('sessions_per_week', 1)
        duration_minutes = subj.get('duration_minutes', slot_len)
        slots_needed = max(1, duration_minutes // slot_len)
        preferred_room = subj.get('preferred_room')
        
        # Validate faculty exists
        if faculty not in faculties:
            raise ValueError(f"Faculty '{faculty}' not found in faculty list: {faculties}")
        
        # create that many LectureReqs
        for _ in range(sessions_per_week):
            reqs.append(LectureReq(timetable_name, subj_code, subj_name, faculty, slots_needed, preferred_room))

    # Try randomized restarts to get a valid assignment
    attempts = config.get('attempts_per_timetable', 100)
    for attempt in range(attempts):
        assignments = shuffle_and_try_assign(reqs, all_slots, rooms, faculties)
        if assignments is not None:
            # build human-readable schedule table
            schedule = []
            for uid, (slot_ids, room, req) in assignments.items():
                for sid in slot_ids:
                    # parse sid to get day/slot
                    # sid format: D{d}_S{si}
                    parts = sid.split('_')
                    day_idx = int(parts[0][1:])
                    slot_idx = int(parts[1][1:])
                    # find actual Slot object
                    sobj = next((s for s in all_slots if s.day_index == day_idx and s.slot_index == slot_idx), None)
                    # compute end time for the base slot
                    fmt = "%H:%M"
                    if sobj and sobj.start_time_str:
                        start_dt = datetime.strptime(sobj.start_time_str, fmt)
                        end_dt = start_dt + timedelta(minutes=slot_len)
                        # Format as 12-hour with am/pm
                        start_time_str = start_dt.strftime("%I:%M %p").lower()
                        end_time_str = end_dt.strftime("%I:%M %p").lower()
                    else:
                        start_time_str = ''
                        end_time_str = ''
                    schedule.append({
                        'day': day_names[day_idx] if day_idx < len(day_names) else f"Day {day_idx+1}",
                        'start_time': start_time_str,
                        'end_time': end_time_str,
                        'room': room,
                        'subject_code': req.subject_code,
                        'subject_name': req.subject_name,
                        'faculty': req.faculty
                    })
            return schedule
    return None


def generate_multiple_timetables(config):
    n = config['num_timetables']
    names = config.get('timetable_names') or [f"TT_{i+1}" for i in range(n)]
    assert len(names) >= n, "Provide at least `num_timetables` names or leave timetable_names empty to auto-generate."

    results = {}
    seeds_tried = set()
    max_overall_attempts = config.get('max_overall_attempts', 500)
    overall_attempts = 0
    i = 0
    while i < n and overall_attempts < max_overall_attempts:
        overall_attempts += 1
        seed = random.randint(1, 10**9)
        if seed in seeds_tried:
            continue
        seeds_tried.add(seed)
        schedule = generate_single_timetable(config, names[i], random_seed=seed)
        if schedule is not None:
            results[names[i]] = schedule
            i += 1
        # else try another seed
    return results


# --------------------------- I/O & CLI -------------------------------------

def save_schedule_csv(schedule, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    keys = ['day', 'start_time', 'end_time', 'room', 'subject_code', 'subject_name', 'faculty']
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in schedule:
            writer.writerow(row)


def save_schedule_json(schedule, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(schedule, f, indent=2)


def interactive_config_prompt():
    print("Let's build the timetable configuration. You can also create a JSON file and pass it with --config.")
    cfg = {}
    cfg['num_timetables'] = int(input('Number of timetables to generate: '))
    names = input('Provide comma-separated names for timetables (leave blank to auto-generate): ') or ''
    cfg['timetable_names'] = [n.strip() for n in names.split(',')] if names else []
    cfg['working_days'] = int(input('Number of working days per week (e.g. 5): '))
    # Accept 12-hour inputs and convert to 24-hour for internal use
    day_start_in = input('Day start time (12-hour, e.g., 9:00 am): ') or '9:00 am'
    day_end_in = input('Day end time (12-hour, e.g., 5:00 pm): ') or '5:00 pm'
    def _to_24h_cli(s):
        fmts = ["%I:%M %p", "%I %p", "%H:%M"]
        for f in fmts:
            try:
                return datetime.strptime(s.strip(), f).strftime("%H:%M")
            except Exception:
                pass
        return s
    cfg['day_start'] = _to_24h_cli(day_start_in)
    cfg['day_end'] = _to_24h_cli(day_end_in)
    cfg['lecture_slot_length_minutes'] = int(input('Lecture slot length in minutes (e.g. 50): ') or '50')
    # Recess is auto-placed near mid-day only if working duration >= 4 hours
    # Rooms
    rooms = []
    print('Enter room names one per line. Blank line to finish:')
    while True:
        r = input('Room name: ').strip()
        if not r:
            break
        rooms.append({'name': r})
    cfg['rooms'] = rooms
    # Faculties
    facs = []
    print('Enter faculty names one per line. Blank line to finish:')
    while True:
        f = input('Faculty name: ').strip()
        if not f:
            break
        facs.append({'name': f})
    cfg['faculties'] = facs
    # Subjects
    subs = []
    print('Enter subjects. For each subject, provide: name, code (optional), faculty (exact faculty name), sessions_per_week, duration_minutes, preferred_room (optional)')
    while True:
        name = input('Subject name (blank to finish): ').strip()
        if not name:
            break
        code = input('Code (or press enter to use name): ').strip() or name
        faculty = input('Faculty (must match one of the faculty names you entered): ').strip()
        sessions = int(input('Sessions per week (integer): ').strip() or '1')
        #dur = int(input('Duration minutes per session (e.g. 50): ').strip() or str(cfg['lecture_slot_length_minutes']))
        pref = input('Preferred room (optional): ').strip() or None
        subs.append({'name': name, 'code': code, 'faculty': faculty, 'sessions_per_week': sessions, 'preferred_room': pref})
    cfg['subjects'] = subs
    cfg['attempts_per_timetable'] = int(input('Attempts per timetable (for randomized restarts, default 100): ') or '100')
    cfg['num_timetables'] = int(cfg['num_timetables'])
    return cfg


def main():
    parser = argparse.ArgumentParser(description='Timetable generator')
    parser.add_argument('--config', help='Path to JSON config file', default=None)
    parser.add_argument('--output_dir', help='Output folder', default='./outputs')
    args = parser.parse_args()

    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)
    else:
        config = interactive_config_prompt()

    print('Generating timetables...')
    results = generate_multiple_timetables(config)
    if not results:
        print('Failed to generate any valid timetable with the given constraints. Try relaxing constraints or increasing attempts.')
        return
    for name, schedule in results.items():
        csv_path = os.path.join(args.output_dir, f'timetable_{name}.csv')
        json_path = os.path.join(args.output_dir, f'timetable_{name}.json')
        save_schedule_csv(schedule, csv_path)
        save_schedule_json(schedule, json_path)
        print(f'Saved timetable {name} -> {csv_path}, {json_path}')
        headers = ["Day", "Start Time", "End Time", "Room", "Subject", "Faculty"]
        rows = [
            [row["day"], row["start_time"], row.get("end_time", ''), row["room"], row["subject_name"], row["faculty"]]
            for row in sorted(schedule, key=lambda x: (x["day"], x["start_time"]))
        ]
        print(f"\n📅 Timetable: {name}")
        print(tabulate(rows, headers=headers, tablefmt="grid"))

    print('Done.')

if __name__ == '__main__':
    main()
    