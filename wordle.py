#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wordle-terminal — tiny, comfy Wordle clone for your shell

vibe:
- quick to run, zero external deps
- 5 letters, 6 tries, the usual
- color tiles (ANSI) or emoji-only mode
- Hard Mode (you must honor revealed info)
- Daily mode (deterministic by date) or Random/Seeded
- shareable result grid like the OG
- lil' keyboard overlay + super-light stats in ~/.wordle_terminal_stats.json
- ships with a tiny wordlist; you can drop your own words.txt / solutions.txt

usage:
  python3 wordle_terminal.py              # random
  python3 wordle_terminal.py --daily      # word of the day
  python3 wordle_terminal.py --hard       # hard mode
  python3 wordle_terminal.py --emoji      # emoji tiles, no ANSI
  python3 wordle_terminal.py --seed 42    # reproducible
  python3 wordle_terminal.py --words words.txt --solutions solutions.txt

note:
- after a game ends, it asks if you wanna play again (no insta-exit)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# ——— mini built-in wordlists ———
# keep the repo lightweight; toss in your own txts for a bigger pool
BUILTIN_SOLUTIONS = [
    "crane", "slate", "adieu", "stare", "store", "raise", "tears", "alone", "pride", "chaos",
    "flame", "glint", "hover", "mirth", "noble", "ocean", "proud", "quake", "radii", "saint",
    "tangy", "ultra", "vivid", "waltz", "xenon", "young", "zesty", "bloom", "candy", "daisy",
    "eager", "fairy", "gamer", "haven", "ionic", "joule", "kitty", "lemon", "mango", "ninja",
    "opera", "piano", "queen", "robot", "sunny", "tiger", "umbra", "vapor", "wharf", "yield"
]

# acceptable guesses fallback (merge with solutions so you can always guess the answer)
BUILTIN_GUESSES = list({*BUILTIN_SOLUTIONS, *[
    "about","other","which","there","their","would","these","thing","could","first",
    "sound","place","great","again","still","every","small","found","those","never",
]})

# ——— terminal colors ———
class Ansi:
    # raw ESCs confuse editors; use \033
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    BLACK = "\033[30m"; RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
    BLUE = "\033[34m"; MAGENTA = "\033[35m"; CYAN = "\033[36m"; WHITE = "\033[37m"
    BG_GREEN = "\033[42m"; BG_YELLOW = "\033[43m"; BG_GREY = "\033[100m"

# status codes -> easier to style downstream
STATUS = {"correct": "G", "present": "Y", "absent": "B"}
EMOJI = {"G": "🟩", "Y": "🟨", "B": "⬛"}
QWERTY_ROWS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]

# ——— helpers ———

def normalize_word(w: str) -> str:
    # chill: trim and lowercase; caps lock won’t carry you
    return w.strip().lower()

def load_words(paths: List[Path]) -> Tuple[List[str], List[str]]:
    """load (solutions, allowed) from optional files; default to built-ins"""
    solutions: List[str] = []
    allowed: List[str] = []

    for p in paths:
        if not p:
            continue
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                words = [normalize_word(x) for x in f if x.strip()]
            # only clean 5-letter alpha words, no cursed inputs
            words = [w for w in words if len(w) == 5 and w.isalpha()]
            # filename vibe check: 'solutions' = answer pool, everything else = allowed guesses
            if "solution" in p.name.lower():
                solutions.extend(words)
            else:
                allowed.extend(words)

    if not solutions:
        solutions = BUILTIN_SOLUTIONS[:]
    if not allowed:
        allowed = list({*BUILTIN_GUESSES, *solutions})

    # keep order, drop dupes — deterministic ftw
    def dedup(seq: Iterable[str]) -> List[str]:
        seen = set(); out = []
        for x in seq:
            if x not in seen:
                seen.add(x); out.append(x)
        return out

    return dedup(solutions), dedup(allowed)

def pick_target(solutions: List[str], daily: bool, seed: Optional[int]) -> str:
    # daily = deterministic by date (UTC); same puzzle for everyone that day
    if daily:
        today = dt.date.today()
        epoch = dt.date(2021, 6, 19)  # random-ish anchor around Wordle’s rise
        idx = (today - epoch).days % len(solutions)
        return solutions[idx]
    rng = random.Random(seed) if seed is not None else random.Random()
    return rng.choice(solutions)

def score_guess(guess: str, target: str) -> List[str]:
    """classic green/yellow/black scoring with proper duplicate handling"""
    guess = guess.lower(); target = target.lower()
    status = ["B"] * 5
    leftover: Dict[str, int] = {}

    # pass 1: greens + count leftovers from target
    for i, (g, t) in enumerate(zip(guess, target)):
        if g == t:
            status[i] = "G"
        else:
            leftover[t] = leftover.get(t, 0) + 1

    # pass 2: yellows if the letter still has remaining count
    for i, g in enumerate(guess):
        if status[i] == "G":
            continue
        if leftover.get(g, 0) > 0:
            status[i] = "Y"
            leftover[g] -= 1
    return status

def enforce_hard_mode(guesses: List[str], statuses: List[List[str]], candidate: str) -> Tuple[bool, str]:
    """Hard Mode rules: lock greens; include revealed letters (with counts)."""
    candidate = candidate.lower()
    must_have_counts: Dict[str, int] = {}
    locked_positions: Dict[int, str] = {}

    for guess, st in zip(guesses, statuses):
        for i, (ch, s) in enumerate(zip(guess, st)):
            if s == "G":
                locked_positions[i] = ch
            if s in ("G", "Y"):
                have = sum(1 for a, b in zip(guess, st) if a == ch and b in ("G", "Y"))
                must_have_counts[ch] = max(must_have_counts.get(ch, 0), have)

    for pos, ch in locked_positions.items():
        if candidate[pos] != ch:
            return False, f"Hard mode: position {pos+1} must be '{ch.upper()}'."

    for ch, cnt in must_have_counts.items():
        if candidate.count(ch) < cnt:
            return False, f"Hard mode: include {cnt}x '{ch.upper()}'."

    return True, ""

def print_board(guesses: List[str], statuses: List[List[str]], use_color: bool, emoji_mode: bool):
    # renders the rows — ANSI blocks or emoji squares; both cozy
    def cell(ch: str, s: str) -> str:
        if emoji_mode or not use_color:
            return EMOJI[s]
        if s == "G":
            return f"{Ansi.BG_GREEN}{Ansi.WHITE} {ch.upper()} {Ansi.RESET}"
        if s == "Y":
            return f"{Ansi.BG_YELLOW}{Ansi.WHITE} {ch.upper()} {Ansi.RESET}"
        return f"{Ansi.BG_GREY}{Ansi.WHITE} {ch.upper()} {Ansi.RESET}"

    for guess, st in zip(guesses, statuses):
        if not guess:
            print("   ".join(["[ _ ]"] * 5))
        else:
            print(" ".join(cell(ch, s) for ch, s in zip(guess, st)))

def print_keyboard(guesses: List[str], statuses: List[List[str]], use_color: bool, emoji_mode: bool):
    # quick keyboard heatmap so your brain keeps up
    best: Dict[str, str] = {}
    order = {"B": 0, "Y": 1, "G": 2}
    for guess, st in zip(guesses, statuses):
        for ch, s in zip(guess.upper(), st):
            if ch not in best or order[s] > order[best[ch]]:
                best[ch] = s

    def style_key(ch: str) -> str:
        s = best.get(ch)
        if s is None:
            return ch
        if emoji_mode or not use_color:
            return {"G":"🟩","Y":"🟨","B":"⬛"}[s] + ch
        if s == "G":
            return f"{Ansi.BG_GREEN}{Ansi.WHITE}{ch}{Ansi.RESET}"
        if s == "Y":
            return f"{Ansi.BG_YELLOW}{Ansi.WHITE}{ch}{Ansi.RESET}"
        return f"{Ansi.BG_GREY}{Ansi.WHITE}{ch}{Ansi.RESET}"

    for row in QWERTY_ROWS:
        print(" ".join(style_key(c) for c in row))
    print()  # lil' spacer

def save_stats(win: bool, guesses_used: Optional[int]):
    # tiny JSON in your home dir; if it borks, we fail soft
    path = Path.home() / ".wordle_terminal_stats.json"
    data = {
        "played": 0,
        "wins": 0,
        "current_streak": 0,
        "max_streak": 0,
        "dist": {str(i): 0 for i in range(1, 7)},
        "fails": 0,
    }
    if path.exists():
        try:
            data.update(json.loads(path.read_text()))
        except Exception:
            pass  # not worth crashing the vibe

    data["played"] += 1
    if win:
        data["wins"] += 1
        data["current_streak"] += 1
        data["max_streak"] = max(data["max_streak"], data["current_streak"])
        if guesses_used is not None:
            k = str(guesses_used)
            data["dist"][k] = data["dist"].get(k, 0) + 1
    else:
        data["fails"] += 1
        data["current_streak"] = 0

    try:
        path.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

    return data

def print_stats(data: Dict[str, int]):
    # no charts, just the numbers you care about
    played = data.get("played", 0)
    wins = data.get("wins", 0)
    winrate = int(round((wins / played) * 100)) if played else 0
    print(f"Games: {played}  •  Wins: {wins}  •  Win%: {winrate}  •  Streak: {data.get('current_streak',0)} (max {data.get('max_streak',0)})")
    print("Guess distribution:")
    dist = data.get("dist", {})
    for i in range(1, 7):
        n = dist.get(str(i), 0)
        bar = "#" * n
        print(f" {i}: {bar}")

def make_share_text(title: str, statuses: List[List[str]]) -> str:
    # build the little grid you can paste anywhere (always emoji for share)
    lines = []
    for st in statuses:
        if st:
            lines.append("".join(EMOJI[x] for x in st))
    return title + "\n" + "\n".join(lines)

# ——— one game session ———

def play_one_game(solutions: List[str], allowed: List[str], args) -> None:
    use_color = not args.no_color and not args.emoji and sys.stdout.isatty()

    target = pick_target(solutions, daily=args.daily, seed=args.seed)

    title = "Wordle-T (6)"
    if args.daily:
        title = f"Wordle-T Daily {dt.date.today().isoformat()}"
    if args.seed is not None and not args.daily:
        title += f" [seed {args.seed}]"

    print(Ansi.BOLD + title + Ansi.RESET)
    if args.hard:
        print("Hard mode ON")
    print("Type a 5-letter word. Enter to submit. Ctrl+C to quit.\n")

    guesses: List[str] = []
    statuses: List[List[str]] = []

    MAX_GUESSES = 6
    while len(guesses) < MAX_GUESSES:
        # draw board + keyboard each turn so you see the whole picture
        placeholders = [""] * (MAX_GUESSES - len(guesses))
        print_board(guesses + placeholders, statuses + [[] for _ in placeholders], use_color, args.emoji)
        print_keyboard(guesses, statuses, use_color, args.emoji)

        try:
            raw = input(f"Guess {len(guesses)+1}/{MAX_GUESSES}: ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            return

        guess = normalize_word(raw)
        if len(guess) != 5 or not guess.isalpha():
            print("Please enter a valid 5-letter word.\n")
            continue
        if guess not in allowed:
            print("Word not in list (add it to words.txt to allow).\n")
            continue
        if args.hard:
            ok, reason = enforce_hard_mode(guesses, statuses, guess)
            if not ok:
                print(reason + "\n")
                continue

        st = score_guess(guess, target)
        guesses.append(guess)
        statuses.append(st)

        if guess == target:
            print_board(guesses, statuses, use_color, args.emoji)
            print_keyboard(guesses, statuses, use_color, args.emoji)
            print(Ansi.GREEN + Ansi.BOLD + f"✅ You win in {len(guesses)}/{MAX_GUESSES}!" + Ansi.RESET)
            data = save_stats(True, len(guesses))
            print_stats(data)
            print("\nShare:")
            print(make_share_text(title + f" {len(guesses)}/{MAX_GUESSES}", statuses))
            return

    # out of tries — still love u tho
    print_board(guesses, statuses, use_color, args.emoji)
    print_keyboard(guesses, statuses, use_color, args.emoji)
    print(Ansi.RED + Ansi.BOLD + f"❌ You lose. The word was: {target.upper()}" + Ansi.RESET)
    data = save_stats(False, None)
    print_stats(data)
    print("\nShare:")
    print(make_share_text(title + " X/6", statuses))

# ——— main loop (stays open after a game) ———

def main():
    parser = argparse.ArgumentParser(description="Wordle in Terminal — Python")
    parser.add_argument("--daily", action="store_true", help="Word of the day (deterministic)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible game")
    parser.add_argument("--hard", action="store_true", help="Hard mode (enforce hints)")
    parser.add_argument("--emoji", action="store_true", help="Emoji-only tiles (no ANSI colors)")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument("--words", type=str, default=None, help="Path to custom word list (words.txt)")
    parser.add_argument("--solutions", type=str, default=None, help="Path to custom solutions list (solutions.txt)")
    args = parser.parse_args()

    # gather wordlists (auto-detect local txts)
    list_paths = []
    if args.words:
        list_paths.append(Path(args.words))
    if args.solutions:
        list_paths.append(Path(args.solutions))
    for name in ("words.txt", "solutions.txt"):
        p = Path(name)
        if p.exists():
            list_paths.append(p)

    solutions, allowed = load_words(list_paths)

    # keep the terminal alive: play again until you say no
    while True:
        play_one_game(solutions, allowed, args)
        try:
            again = input("\nPlay again? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if again not in ("y", "yes"):
            print("Okay, gg. 👋")
            break

if __name__ == "__main__":
    main()
