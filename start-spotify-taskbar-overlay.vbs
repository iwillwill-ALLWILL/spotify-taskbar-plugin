Option Explicit
Dim shell, fso, root, pyw, script, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then
  pyw = "pythonw.exe"
End If
script = root & "\spotify_taskbar_tray.py"
cmd = Chr(34) & pyw & Chr(34) & " " & Chr(34) & script & Chr(34)
shell.Run cmd, 0, False
