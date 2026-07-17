# Lessons

- **Don't contradict the user's observed behavior from model memory.** When the user says something works in their environment (e.g., Ghostty loads `config.ghostty` from `~/Library/Application Support/com.mitchellh.ghostty/`), verify empirically before "correcting" them — a marker-file test with `ghostty +show-config` settled it in seconds. Ghostty ≥1.3 loads `*.ghostty` files from its config dir, not only the bare `config` file.
