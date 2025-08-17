````markdown
# wordle-terminal 🎮

Tiny Wordle clone for your terminal — zero deps, pure Python.  
6 tries, 5 letters, cozy ANSI colors or emoji squares.  
Stats are saved locally, you can share your result grid like the OG.  

---

## ✨ Features
- 🟩 Classic Wordle rules (5 letters, 6 guesses)  
- 🌈 ANSI color tiles (or emoji-only mode if you prefer)  
- 🔒 Hard Mode — forces you to respect known hints  
- 📅 Daily puzzle (deterministic) or random/seeded  
- ⌨️ Mini keyboard overlay in terminal  
- 📊 Local stats in `~/.wordle_terminal_stats.json`  
- 📝 Custom wordlists supported (`words.txt` / `solutions.txt`)  

---

## 🚀 Usage
Run directly with Python 3:

```bash
python3 wordle_terminal.py            # random word
python3 wordle_terminal.py --daily    # daily word
python3 wordle_terminal.py --hard     # hard mode
python3 wordle_terminal.py --emoji    # emoji squares, no ANSI
python3 wordle_terminal.py --seed 42  # reproducible run
python3 wordle_terminal.py --words words.txt --solutions solutions.txt
````

When a game ends, you’ll be asked if you want to play again.
Stats + streaks are tracked automatically.

---

## 📸 Example (emoji mode)

```
⬛⬛🟨⬛⬛
⬛🟨⬛🟩⬛
⬛⬛🟩⬛🟩
⬛⬛⬛🟩🟩
🟩🟩🟩🟩🟩
```

`Wordle-T Daily 2025-08-17 5/6`

---

## 🔧 Contribute

PRs, wordlist improvements, and cool ideas welcome ✨
Feel free to fork and play around.

---

## 📄 License

MIT — do whatever, just don’t blame me if you ragequit after 6 fails 😉

```
