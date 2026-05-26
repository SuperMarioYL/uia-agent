# vhs script for the README demo gif.
#
# Real recording is a manual follow-up — vhs needs a Windows session with
# Notepad already open + a valid ANTHROPIC_API_KEY (or OPENAI_API_KEY).
#
#   1. Install vhs:           https://github.com/charmbracelet/vhs
#   2. Run on Windows:        vhs assets/demo.tape
#   3. Output:                assets/demo.gif (30s, 800x500)
#
# Embed once recorded:
#   ![demo](assets/demo.gif)

Output assets/demo.gif

Set FontSize 14
Set Width 800
Set Height 500
Set Padding 20
Set Theme "Catppuccin Mocha"

Type "# Show the pruned UIA tree of the focused Notepad window"
Enter
Sleep 500ms

Type "uia-agent dump --app Notepad | head -40"
Enter
Sleep 3s

Type "clear"
Enter
Sleep 500ms

Type "# Drive Notepad in one sentence — the agent enumerates UIA, types,"
Enter
Type "# opens File > Save As, fills the dialog, and clicks Save."
Enter
Sleep 1s

Type `uia-agent run --app Notepad "type a haiku about Windows 95, save it as poem.txt to the desktop"`
Enter
Sleep 22s

Type "ls ~/Desktop/poem.txt"
Enter
Sleep 2s
