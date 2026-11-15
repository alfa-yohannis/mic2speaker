"""Audio devices, filters, and the per-operating-system adapters that use them.

The form depends only on three interfaces:

    AudioDeviceProvider  lists the microphones and speakers.
    AudioLoopback        plays a microphone through a speaker, with optional
                         filters and a volume.
    AudioDeviceWatcher   reports when devices are plugged in or out.

Each operating system gets its own subclass of each. Linux has
LinuxAudioDeviceProvider, LinuxAudioLoopback, and LinuxAudioDeviceWatcher;
Windows adapters can be added next to them later.
"""
