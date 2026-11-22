Option Explicit
Dim shell, fso, base, python, entry
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
python = fso.BuildPath(base, ".venv\Scripts\pythonw.exe")
entry = fso.BuildPath(base, "queue_main.py")
If Not fso.FileExists(python) Then
    MsgBox "Please run setup.bat first.", vbInformation, "AudioExtract Queue"
    WScript.Quit 1
End If
shell.CurrentDirectory = base
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & entry & Chr(34), 0, False
