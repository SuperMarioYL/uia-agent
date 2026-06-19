# vhs tape — uia-agent happy path.
# Render in CI via .github/workflows/demo.yml, or locally:
#   vhs docs/demo.tape   (needs the `uia-agent` CLI on PATH)
#
# The end-to-end `run`/`dump` commands drive a live app via the Windows UIA
# tree, so the full screencast is recorded on a Windows session with Notepad
# open and ANTHROPIC_API_KEY (or OPENAI_API_KEY) set. The CI render below
# exercises the CLI surface so the tape always stays in sync with the binary.
Output assets/demo.gif

Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 640
Set Theme "Dracula"
Set Padding 18

Type "# uia-agent — drive legacy Windows apps via the UIA accessibility tree"
Enter
Sleep 800ms

Type "uia-agent --help"
Enter
Sleep 2.5s

Type "# 1) Dump the focused window's pruned UIA tree as JSON (debug aid)"
Enter
Sleep 600ms
Type "uia-agent dump --app Notepad | head -40"
Enter
Sleep 3s

Type "# 2) Drive Notepad in one sentence — observe -> think -> act, one step at a time"
Enter
Sleep 600ms
Type `uia-agent run --app Notepad "type a haiku about Windows 95 and save it as poem.txt on the desktop"`
Enter
Sleep 4s
