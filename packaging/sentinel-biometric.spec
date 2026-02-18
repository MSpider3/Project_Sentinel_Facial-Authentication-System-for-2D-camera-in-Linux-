Name:           sentinel-biometric
Version:        1.0.0
Release:        1%{?dist}
Summary:        Advanced biometric authentication system for Linux

License:        MIT
URL:            https://github.com/yourusername/project-sentinel
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  vala
BuildRequires:  meson
BuildRequires:  ninja-build
BuildRequires:  gtk4-devel
BuildRequires:  json-glib-devel
BuildRequires:  gstreamer1-devel
BuildRequires:  python3-devel

Requires:       gtk4
Requires:       python3
Requires:       python3-numpy
Requires:       python3-opencv
Requires:       python3-scipy
Requires:       polkit

%description
Project Sentinel is a software-defined biometric security system that provides
advanced facial recognition using standard 2D webcams. Features anti-spoofing,
liveness detection, and adaptive learning.

%prep
%autosetup

%build
# Build Vala GTK4 app
meson setup builddir
ninja -C builddir

# Create Python venv for runtime
python3 -m venv %{_builddir}/venv
%{_builddir}/venv/bin/pip install -r requirements.txt

%install
# Install binary
install -Dm755 builddir/sentinel-ui %{buildroot}%{_bindir}/sentinel-gui-real
install -Dm755 sentinel_service.py %{buildroot}%{_libexecdir}/sentinel/sentinel_service.py
install -Dm755 biometric_processor.py %{buildroot}%{_libexecdir}/sentinel/biometric_processor.py
install -Dm755 camera_stream.py %{buildroot}%{_libexecdir}/sentinel/camera_stream.py
install -Dm755 spoof_detector.py %{buildroot}%{_libexecdir}/sentinel/spoof_detector.py
install -Dm755 stability_tracker.py %{buildroot}%{_libexecdir}/sentinel/stability_tracker.py

# Install Python venv
cp -r %{_builddir}/venv %{buildroot}%{_libexecdir}/sentinel/

# Install models
install -Dm644 models/*.onnx -t %{buildroot}%{_datadir}/sentinel/models/

# Install config
install -Dm644 config.ini %{buildroot}%{_sysconfdir}/project-sentinel/config.ini

# Install PolicyKit policy
install -Dm644 packaging/com.sentinel.policy %{buildroot}%{_datadir}/polkit-1/actions/com.sentinel.policy

# Install launcher wrapper
install -Dm755 packaging/sentinel-gui %{buildroot}%{_bindir}/sentinel-gui

# Install desktop file
install -Dm644 packaging/sentinel-gui.desktop %{buildroot}%{_datadir}/applications/sentinel-gui.desktop

# Install icon (you'll need to add this)
# install -Dm644 icons/sentinel.png %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/sentinel.png

%files
%license LICENSE
%doc README.md
%{_bindir}/sentinel-gui
%{_bindir}/sentinel-gui-real
%{_libexecdir}/sentinel/
%{_datadir}/sentinel/
%{_sysconfdir}/project-sentinel/
%{_datadir}/polkit-1/actions/com.sentinel.policy
%{_datadir}/applications/sentinel-gui.desktop
# %{_datadir}/icons/hicolor/256x256/apps/sentinel.png

%post
# Create secure directories
mkdir -p /var/lib/project-sentinel/{models,blacklist}
chmod 700 /var/lib/project-sentinel
chmod 700 /var/lib/project-sentinel/models
chmod 700 /var/lib/project-sentinel/blacklist

%changelog
* Wed Jan 22 2026 Your Name <your.email@example.com> - 1.0.0-1
- Initial RPM release
- Root-level security with PolicyKit integration
- GTK4 interface for enrollment and management
