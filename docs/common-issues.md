# Common issues

## No backend available YubiKey error

```
NoBackendError('No backend available')
```

This issue can happen on Windows when trying to connect to a YubiKey. This is a generic issue that
can occur when using `PyUSB` to connect to a USB device and is not specific to communication with a YubiKey.
`PyUSB` will search for `libusb-1.0`, `libusb0`, and `openUSB` backends.

**The issue is solved by downloading  and installing `Libusb Win32 Driver`.**

