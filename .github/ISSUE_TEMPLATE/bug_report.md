---
name: Bug report
about: Something isn't working
labels: bug
---

**What happened**

**Expected**

**Role / version**
- role: hub / sensor
- `netsentinel version`:
- OS: Raspberry Pi OS Bookworm 64-bit / other

**Logs**
```
journalctl -u netsentinel-<role> -n 100 --no-pager
```

**Config (redact the token)**
```
netsentinel config
```
