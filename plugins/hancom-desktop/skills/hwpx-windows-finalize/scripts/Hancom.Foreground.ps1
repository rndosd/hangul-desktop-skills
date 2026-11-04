# Keeps the person's window in front while an owned Hangul instance starts and quits.
# A COM-created Hangul comes to the front before it can be hidden, and when it hides or quits Windows raises
# whatever window lies behind (a messenger, another browser): typing then lands in the wrong window. These
# helpers only give the focus back to the window that was in front before Hangul started, and only when Hangul
# (or the bare desktop) took it, or the quit just moved it; a window the person chose meanwhile is left alone.
if (-not ('HancomForeground' -as [type])) {
    Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class HancomForeground {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr window);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint attach, uint to, bool on);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    public static bool Restore(IntPtr window) {
        if (window == IntPtr.Zero || !IsWindow(window)) return false;
        IntPtr now = GetForegroundWindow();
        if (now == window) return true;
        uint ignored; uint front = GetWindowThreadProcessId(now, out ignored); uint me = GetCurrentThreadId();
        bool attached = front != 0 && front != me && AttachThreadInput(me, front, true);  // the front thread may hand over focus
        bool done = SetForegroundWindow(window);
        if (attached) AttachThreadInput(me, front, false);
        return done;
    }
}
'@
}

function Get-HancomPersonWindow { return [HancomForeground]::GetForegroundWindow() }

function Get-HancomWindowProcess([IntPtr]$Window) {
    if ($Window -eq [IntPtr]::Zero) { return '' }
    [uint32]$owner = 0; [void][HancomForeground]::GetWindowThreadProcessId($Window, [ref]$owner)
    if (-not $owner) { return '' }
    try { return (Get-Process -Id $owner -ErrorAction Stop).ProcessName } catch { return '' }
}

function Restore-HancomPersonWindowAfterStart([IntPtr]$Window) {
    # after the owned Hangul is hidden: give the focus back if Hangul or the shell holds it
    if ($Window -eq [IntPtr]::Zero) { return }
    $now = [HancomForeground]::GetForegroundWindow()
    if ($now -ne $Window -and (Get-HancomWindowProcess $now) -in @('Hwp', 'explorer', '')) { [void][HancomForeground]::Restore($Window) }
}

function Invoke-HancomQuitKeepingFocus([scriptblock]$Quit, [IntPtr]$Window) {
    # run the quit; if the window in front changed during it (Windows raised the next one), put the person's back
    $before = [HancomForeground]::GetForegroundWindow()
    $ours = $before -eq $Window -or (Get-HancomWindowProcess $before) -in @('Hwp', 'explorer', '')
    & $Quit
    if ($Window -eq [IntPtr]::Zero -or -not $ours) { return }  # the person moved on to another window: leave it
    for ($i = 0; $i -lt 10; $i++) {  # the raise follows the quit within a moment
        Start-Sleep -Milliseconds 100
        if ([HancomForeground]::GetForegroundWindow() -ne $Window) { [void][HancomForeground]::Restore($Window); return }
    }
}
