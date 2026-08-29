import subprocess
import time

ADB = r"C:\Android\sdk\platform-tools\adb.exe"

def adb_shell(*args):
    return subprocess.run([ADB, "shell", *args], capture_output=True, text=True)

# 1. Tap Email text field (right side to ensure cursor is at the end)
adb_shell("input", "tap", "800", "560")
time.sleep(0.3)

# 2. Backspace 40 times to clear %40gmail.com and username
adb_shell("input", "keyevent", *["67"] * 45)
time.sleep(0.3)

# 3. Type proper email with @ keyevent
adb_shell("input", "text", "imharshofficial322")
adb_shell("input", "keyevent", "77")  # @
adb_shell("input", "text", "gmail.com")
time.sleep(0.4)

# 4. Hide keyboard
adb_shell("input", "keyevent", "4")
time.sleep(0.5)

# 5. Tap Sign In button (x=540, y=1680)
adb_shell("input", "tap", "540", "1680")
time.sleep(1.5)
print("Submitted login!")
