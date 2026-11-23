import sys, glob
from lupa import lua51
lua = lua51.LuaRuntime()
load = lua.eval("function(src, name) local f, err = loadstring(src, name) return err end")
bad = 0
for path in sorted(glob.glob(sys.argv[1] + "/*.lua")):
    err = load(open(path, encoding="utf-8").read(), "@" + path.split("\\")[-1].split("/")[-1])
    print(("OK   " if err is None else "FAIL ") + path.split("/")[-1].split("\\")[-1] + ("" if err is None else ": " + err))
    bad += err is not None
sys.exit(bad)
