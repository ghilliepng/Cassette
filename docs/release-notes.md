## {name} {version}

**Download:** `{setup}`, below. Run it, and Cassette goes in your Start menu and system tray. It
finds WoW Forever and installs the addon if you don't have it yet.

### "Windows protected your PC"?

That's expected. Cassette isn't signed with a paid code-signing certificate, so Windows doesn't
know its publisher yet. Click **More info**, then **Run anyway**.

Cassette is free, and all its code is public: everything in this release is built from the code in this
repository. To check that your download is this exact file, run this in PowerShell (with your
download's path):

```
Get-FileHash "$env:USERPROFILE\Downloads\{setup}"
```

It should print this SHA-256:

```
{sha256}
```

### What's new

- (fill in)
