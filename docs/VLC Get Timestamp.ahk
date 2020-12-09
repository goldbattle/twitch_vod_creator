; # Insert Timestamp from VLC
; https://superuser.com/a/1329884
F8::
    WinGet, winid,, A ; # Save the current window
    ; GoToTimeDialogName:="Zu Zeitpunkt gehen" ; # german name of "Go to Time" dialog
    GoToTimeDialogName:="Go to Time" ; # english name of "Go to Time" dialog
    ClipSaved := ClipboardAll ; # Save the entire clipboard
    MouseGetPos x, y ; # get current mouse position
    if WinExist("ahk_exe vlc.exe") { ; # if vlc existst, i.e. vlc is running
        WinActivate ; # activate vlc window
        Send, {Esc} ; # make sure you are not in other dialogs
        Send, ^t ; # open the "Go to Time" dialog
        if WinExist(GoToTimeDialogName) { ; # if the "Go to Time" dialog exists
            WinActivate ; # activate "Go to Time" dialog exists
            ; MouseClick, left, 120, 48 ; # click on time field (change this for other screen resolutions)
            Send, ^a ; # select time field
            Send, ^c ; # copy to clipboard
            ClipWait ; # Wait for the clipboard to contain text.
            ts:=clipboard ; # get content of clipboard to var "ts"
            ts:= StrReplace(ts, "H", "")
            ts:= StrReplace(ts, "m", "")
            ts:= StrReplace(ts, "s", "")
            Clipboard := ts
            Send, ^t ; # quit "Go to Time" dialog
        }
    }
    ; MouseMove %x%, %y% ; # move mouse to original position
    IfWinExist, ahk_id %winid% ; # go back to the original program (non-vlc)
        WinActivate
    return
