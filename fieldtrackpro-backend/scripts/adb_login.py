import subprocess
import time

ADB = r"C:\Android\sdk\platform-tools\adb.exe"

def adb(*args):
    return subprocess.run([ADB, *args], capture_output=True, text=True)

def adb_shell(*args):
    return adb("shell", *args)

# 1. Tap Email field (when keyboard is open, y is around 520)
adb_shell("input", "tap", "540", "520")
time.sleep(0.3)

# Select all and delete
adb_shell("input", "keyevent", "--longpress", "67")
for _ in range(35):
    adb_shell("input", "keyevent", "67")

# Type email: imharshofficial322 + @ + gmail.com
adb_shell("input", "text", "imharshofficial322")
adb_shell("input", "keyevent", "77")  # KEYCODE_AT
adb_shell("input", "text", "gmail.com")
time.sleep(0.3)

# 2. Tap Password field
adb_shell("input", "tap", "540", "615")
time.sleep(0.3)

# Clear password
for _ in range(25):
    adb_shell("input", "keyevent", "67")

# Type password: Imharsh + @ + 1
adb_shell("input", "text", "Imharsh")
adb_shell("input", "keyevent", "77")  # KEYCODE_AT
adb_shell("input", "text", "1")
time.sleep(0.3)

# 3. Hide keyboard
adb_shell("input", "keyevent", "4")  # KEYCODE_BACK
time.sleep(0.5)

# 4. Tap Sign In button (when keyboard closed, center is 540, 1630)
adb_shell("input", "tap", "540", "1630")
time.sleep(1.0)
print("Login sequence complete!")
