%global debug_package %{nil}

Name:           gsp670-linux
Version:        0.1.0
Release:        1%{?dist}
Summary:        Linux support for the EPOS|Sennheiser GSP 670 headset and GSA 70 dongle

License:        MIT
URL:            https://github.com/mrcanofcatfood/gsp670-linux
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-build

# The audio path needs no package from this project: the stereo "Game" sink
# and the mono "Chat" sink come from the stock usb-gaming-headset.conf ALSA
# profile set that ships with PulseAudio/ALSA.
Requires:       python3-hidapi
Recommends:     pipewire
Recommends:     wireplumber
Suggests:       python3-dbus
Suggests:       python3-gobject

%description
This package provides Linux support for the EPOS|Sennheiser GSP 670 wireless
gaming headset and the GSA 70 wireless dongle.

It installs the udev rules that grant hidraw access to the device, a systemd
unit that recovers the ALSA card when the kernel binds the audio interfaces
without registering one, and a WirePlumber configuration that keeps the
USB-audio nodes from being torn down while idle.

The optional Python library adds device controls: sidetone, noise reduction and
auto-power-off, plus device identity and event monitoring.

Note that the GSA 70 dongle firmware has a bug that adds roughly 1.4 seconds of
audio latency. Wired USB-C mode has about 44 ms latency.

%package dbus
Summary:        D-Bus service for the EPOS|Sennheiser GSP 670 headset
Requires:       %{name}%{?_isa} = %{version}-%{release}
Requires:       python3-dbus
Requires:       python3-gobject

%description dbus
Exposes the GSP 670 device controls (sidetone, noise reduction, auto power off)
and link/battery state on the system D-Bus, so that desktop environments and
control panels can reach them.

%prep
%autosetup

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l gsp670

install -Dm644 udev/99-gsp670.rules \
    %{buildroot}%{_prefix}/lib/udev/rules.d/99-gsp670.rules
install -Dm644 udev/99-gsp670-audio.rules \
    %{buildroot}%{_prefix}/lib/udev/rules.d/99-gsp670-audio.rules

install -Dm755 scripts/gsp670-audio-guard.sh \
    %{buildroot}%{_prefix}/lib/gsp670/gsp670-audio-guard.sh

install -Dm644 systemd/gsp670-audio-guard.service \
    %{buildroot}%{_prefix}/lib/systemd/system/gsp670-audio-guard.service
install -Dm644 systemd/gsp670-daemon.service \
    %{buildroot}%{_prefix}/lib/systemd/system/gsp670-daemon.service
install -Dm644 systemd/gsp670-monitor.service \
    %{buildroot}%{_prefix}/lib/systemd/system/gsp670-monitor.service

install -Dm644 contrib/wireplumber/50-gsp670.conf \
    %{buildroot}%{_prefix}/share/wireplumber/wireplumber.conf.d/50-gsp670.conf
install -Dm644 contrib/pipewire/gsp670-virtual-surround-7.1.conf \
    %{buildroot}%{_prefix}/share/pipewire/pipewire.conf.d/50-gsp670-surround.conf

install -Dm644 LICENSE %{buildroot}%{_prefix}/share/licenses/%{name}/LICENSE
install -Dm644 README.md %{buildroot}%{_prefix}/share/doc/%{name}/README.md

%check
# The hardware test needs a physically connected device.
pytest -q tests/unit tests/integration

# The audio guard is opt-in: the package ships the unit but does not enable it.
%files -f %{name}.list
%license %{_prefix}/share/licenses/%{name}/LICENSE
%doc %{_prefix}/share/doc/%{name}/README.md

%files dbus
%{_bindir}/gsp670-daemon
%{_unitdir}/gsp670-daemon.service

%changelog
* Sun Nov 08 2026 gsp670-linux contributors <noreply@example.com> - 0.1.0-1
- Initial release
